"""Catalog services used by the shop and orders apps (docs/contracts/wave-3-commerce.md).

Signatures are frozen by the contract. Everything here is workspace-scoped: pass the workspace
the buyer is shopping in and never trust ids from reply ids without these lookups.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q, QuerySet
from django.utils import timezone

from apps.whatsapp.models import PhoneNumber

from .exceptions import OutOfStock
from .models import Collection, MetaCatalog, MetaCatalogPhoneSetting, Product

__all__ = [
    "CartLine",
    "DroppedLine",
    "OutOfStock",
    "PricedCart",
    "PricedLine",
    "connected_catalog",
    "get_shoppable_product",
    "list_shoppable_collections",
    "list_shoppable_products",
    "price_items",
    "public_image_url",
    "release_stock",
    "reserve_stock",
    "shoppable_products",
]

DROP_UNKNOWN = "unknown"
DROP_INACTIVE = "inactive"
DROP_OUT_OF_STOCK = "out_of_stock"
DROP_QUANTITY_CAPPED = "quantity_capped"


@dataclass(frozen=True)
class CartLine:
    quantity: int
    product_id: uuid.UUID | None = None
    sku: str | None = None


@dataclass(frozen=True)
class PricedLine:
    product: Product
    quantity: int
    unit_price_paise: int
    line_total_paise: int


@dataclass(frozen=True)
class DroppedLine:
    """A cart line that could not be priced as asked.

    ``reason`` is ``unknown``, ``inactive``, ``out_of_stock`` or ``quantity_capped``. A capped
    line still appears in ``PricedCart.lines`` with the reduced quantity (``available``).
    """

    sku: str
    name: str
    reason: str
    requested: int
    available: int | None


@dataclass(frozen=True)
class PricedCart:
    lines: tuple[PricedLine, ...]
    dropped: tuple[DroppedLine, ...]
    subtotal_paise: int

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)


def _as_uuid(value) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def shoppable_products(workspace) -> QuerySet[Product]:
    """Active products buyers can order: in stock and, when tracked, with stock left."""
    return Product.objects.filter(
        workspace=workspace,
        is_active=True,
        availability=Product.Availability.IN_STOCK,
    ).filter(Q(stock_qty__isnull=True) | Q(stock_qty__gt=0))


def list_shoppable_collections(workspace) -> list[Collection]:
    """Active collections with at least one shoppable product, by position then name."""
    with_products = shoppable_products(workspace).filter(collection__isnull=False)
    return list(
        Collection.objects.filter(
            workspace=workspace,
            is_active=True,
            pk__in=with_products.values("collection_id"),
        ).order_by("position", "name", "id")
    )


def list_shoppable_products(
    workspace, *, collection=None, offset: int = 0, limit: int = 9
) -> tuple[list[Product], bool]:
    """A page of shoppable products (optionally of one collection) and whether more follow."""
    offset = max(int(offset), 0)
    limit = max(int(limit), 1)
    queryset = shoppable_products(workspace).select_related("collection")
    if collection is not None:
        collection_id = (
            collection.pk if isinstance(collection, Collection) else _as_uuid(collection)
        )
        if collection_id is None:
            return [], False
        queryset = queryset.filter(collection_id=collection_id)
    page = list(queryset.order_by("position", "name", "id")[offset : offset + limit + 1])
    return page[:limit], len(page) > limit


def get_shoppable_product(workspace, product_id) -> Product | None:
    product_uuid = _as_uuid(product_id)
    if product_uuid is None:
        return None
    return (
        shoppable_products(workspace).select_related("collection").filter(pk=product_uuid).first()
    )


def price_items(workspace, lines: Iterable[CartLine]) -> PricedCart:
    """Re-price cart lines from the database.

    Lines for the same product (by id or SKU) are merged. Unknown and inactive products and
    products buyers see as out of stock are dropped. Quantities are capped at
    ``max_qty_per_order`` and at tracked stock; a capped line is also reported in ``dropped``.
    Prices are ``effective_price_paise`` (the sale price when set).
    """
    wanted = [line for line in lines if isinstance(line.quantity, int) and line.quantity > 0]
    ids = {pid for line in wanted if (pid := _as_uuid(line.product_id)) is not None}
    skus = {line.sku for line in wanted if line.sku}
    products = (
        list(Product.objects.filter(workspace=workspace).filter(Q(pk__in=ids) | Q(sku__in=skus)))
        if ids or skus
        else []
    )
    by_id = {product.pk: product for product in products}
    by_sku = {product.sku: product for product in products}

    merged: dict[tuple[str, str], int] = {}
    resolved: dict[tuple[str, str], Product] = {}
    for line in wanted:
        product = by_id.get(_as_uuid(line.product_id)) if line.product_id is not None else None
        if product is None and line.sku:
            product = by_sku.get(line.sku)
        if product is not None:
            key = ("product", str(product.pk))
            resolved[key] = product
        else:
            key = ("unknown", line.sku or str(line.product_id or ""))
        merged[key] = merged.get(key, 0) + line.quantity

    priced: list[PricedLine] = []
    dropped: list[DroppedLine] = []
    for key, requested in merged.items():
        product = resolved.get(key)
        if product is None:
            dropped.append(DroppedLine(key[1], "", DROP_UNKNOWN, requested, None))
            continue
        if not product.is_active:
            dropped.append(DroppedLine(product.sku, product.name, DROP_INACTIVE, requested, None))
            continue
        if product.buyer_availability == Product.Availability.OUT_OF_STOCK:
            dropped.append(DroppedLine(product.sku, product.name, DROP_OUT_OF_STOCK, requested, 0))
            continue
        allowed = product.max_qty_per_order
        if product.stock_qty is not None:
            allowed = min(allowed, product.stock_qty)
        quantity = min(requested, allowed)
        if quantity < requested:
            dropped.append(
                DroppedLine(product.sku, product.name, DROP_QUANTITY_CAPPED, requested, allowed)
            )
        unit_price = product.effective_price_paise
        priced.append(PricedLine(product, quantity, unit_price, unit_price * quantity))

    return PricedCart(
        lines=tuple(priced),
        dropped=tuple(dropped),
        subtotal_paise=sum(line.line_total_paise for line in priced),
    )


def _merge_stock_lines(lines: Iterable[tuple[uuid.UUID, int]]) -> dict[uuid.UUID, int]:
    merged: dict[uuid.UUID, int] = {}
    for product_id, quantity in lines:
        product_uuid = _as_uuid(product_id)
        if product_uuid is None:
            raise ValueError(f"Invalid product id {product_id!r}.")
        if not isinstance(quantity, int) or quantity < 1:
            raise ValueError(f"Invalid quantity {quantity!r} for product {product_id}.")
        merged[product_uuid] = merged.get(product_uuid, 0) + quantity
    return merged


def reserve_stock(workspace, lines: Iterable[tuple[uuid.UUID, int]]) -> None:
    """Take tracked stock for ``(product_id, quantity)`` lines, all or nothing.

    Each product is decremented with a conditional ``UPDATE ... WHERE stock_qty >= n``, so
    concurrent checkouts can never oversell. Untracked products are skipped. When any line
    can't be reserved, nothing is (a savepoint is rolled back) and :class:`OutOfStock` is
    raised with every failing item. Call inside the caller's ``transaction.atomic``.
    """
    merged = _merge_stock_lines(lines)
    if not merged:
        return
    failures: list[dict] = []
    now = timezone.now()
    with transaction.atomic():
        # A stable lock order keeps concurrent reservations from deadlocking.
        for product_id in sorted(merged, key=str):
            quantity = merged[product_id]
            updated = Product.objects.filter(
                workspace=workspace, pk=product_id, stock_qty__gte=quantity
            ).update(stock_qty=F("stock_qty") - quantity, updated_at=now)
            if updated:
                continue
            product = (
                Product.objects.filter(workspace=workspace, pk=product_id)
                .only("sku", "name", "stock_qty")
                .first()
            )
            if product is not None and product.stock_qty is None:
                continue  # stock is not tracked
            failures.append(
                {
                    "sku": product.sku if product else "",
                    "name": product.name if product else "",
                    "requested": quantity,
                    "available": product.stock_qty if product else 0,
                }
            )
        if failures:
            raise OutOfStock(failures)
    if Product.objects.filter(workspace=workspace, pk__in=merged, stock_qty=0).exists():
        _queue_catalog_sync(workspace)  # sold out: Meta shows it as out of stock


def release_stock(workspace, lines: Iterable[tuple[uuid.UUID, int]]) -> None:
    """Give back tracked stock taken by :func:`reserve_stock`. Untracked or deleted products
    are skipped."""
    merged = _merge_stock_lines(lines)
    if not merged:
        return
    now = timezone.now()
    restocked = Product.objects.filter(workspace=workspace, pk__in=merged, stock_qty=0).exists()
    for product_id in sorted(merged, key=str):
        Product.objects.filter(workspace=workspace, pk=product_id, stock_qty__isnull=False).update(
            stock_qty=F("stock_qty") + merged[product_id], updated_at=now
        )
    if restocked:
        _queue_catalog_sync(workspace)


def _queue_catalog_sync(workspace) -> None:
    from .sync import queue_sync

    queue_sync(workspace.pk)


def public_image_url(product: Product) -> str | None:
    """Absolute public URL of the product image (Meta fetches it), or None without an image.

    Uses ``PUBLIC_MEDIA_BASE_URL`` when set, else ``PUBLIC_API_BASE_URL`` + ``MEDIA_URL``.
    """
    name = product.image.name if product.image else ""
    if not name:
        return None
    path = quote(name, safe="/")
    media_base = settings.PUBLIC_MEDIA_BASE_URL
    if media_base:
        return f"{media_base.rstrip('/')}/{path}"
    media_url = settings.MEDIA_URL or "media/"
    if media_url.startswith(("http://", "https://")):
        return f"{media_url.rstrip('/')}/{path}"
    api_base = settings.PUBLIC_API_BASE_URL.rstrip("/")
    prefix = media_url.strip("/")
    return f"{api_base}/{prefix}/{path}" if prefix else f"{api_base}/{path}"


def meta_catalog_product_counts(meta_catalog: MetaCatalog) -> dict[str, int]:
    """Sync and review counts of the workspace's products (all of them sync to the catalog)."""
    products = Product.objects.filter(workspace_id=meta_catalog.workspace_id)
    return products.aggregate(
        synced=Count("pk", filter=Q(meta_sync_status=Product.SyncStatus.SYNCED)),
        pending=Count("pk", filter=Q(meta_sync_status=Product.SyncStatus.PENDING)),
        failed=Count("pk", filter=Q(meta_sync_status=Product.SyncStatus.FAILED)),
        approved=Count("pk", filter=Q(meta_review_status=Product.ReviewStatus.APPROVED)),
        rejected=Count("pk", filter=Q(meta_review_status=Product.ReviewStatus.REJECTED)),
    )


def meta_catalog_phone_settings(meta_catalog: MetaCatalog) -> list[dict]:
    """``CommerceSettings`` rows for every number on the catalog's WABA (off when unknown)."""
    stored = {
        setting.phone_number_id: setting
        for setting in MetaCatalogPhoneSetting.objects.filter(meta_catalog=meta_catalog)
    }
    rows = []
    numbers = PhoneNumber.objects.filter(
        workspace_id=meta_catalog.workspace_id, waba_id=meta_catalog.waba_id
    ).order_by("created_at", "pk")
    for number in numbers:
        setting = stored.get(number.pk)
        rows.append(
            {
                "phone_number_id": number.pk,
                "display_phone_number": number.display_phone_number,
                "is_cart_enabled": bool(setting and setting.is_cart_enabled),
                "is_catalog_visible": bool(setting and setting.is_catalog_visible),
            }
        )
    return rows


def connected_catalog(workspace, phone_number) -> MetaCatalog | None:
    """The connected Meta catalog of the number's WABA, or None (not connected, or its status is
    ``permissions_missing``/``error``)."""
    if phone_number is None:
        return None
    return (
        MetaCatalog.objects.filter(
            workspace=workspace,
            waba_id=phone_number.waba_id,
            status=MetaCatalog.Status.CONNECTED,
        )
        .select_related("waba")
        .first()
    )
