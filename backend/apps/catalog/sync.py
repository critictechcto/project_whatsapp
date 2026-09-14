"""Meta catalog sync: ``items_batch`` upserts and deletes, batch status and review polling.

- :func:`queue_sync` runs after a product is saved, imported, or has its image changed or stock
  cross zero. It queues one ``catalog.sync_products`` per connected catalog, debounced through
  the cache.
- :func:`run_sync` sends the products changed since the catalog's ``last_synced_at``. Active
  products with an image are upserted, while products that became inactive or lost their image
  are deleted from Meta. A full resync sends everything.
- :func:`poll_pending_batches` (``catalog.poll_sync_status``) finishes ``CatalogSyncBatch`` rows
  and copies Meta's review status onto products.

Meta needs a public ``image_link``, so products without an image stay ``not_synced``. ``link`` is
the store link ``https://wa.me/<digits>?text=Hi`` of the catalog's WhatsApp number.
"""

import logging
import re
from collections import defaultdict
from datetime import timedelta
from functools import partial

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.whatsapp.client import GraphAPIError, get_client
from apps.whatsapp.client.errors import GraphPermissionError, RateLimitedError, TokenInvalidError
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.realtime import broadcast

from .models import CatalogSyncBatch, MetaCatalog, Product
from .services import public_image_url

logger = logging.getLogger(__name__)

SYNC_FRAME = "catalog.sync"
SYNC_DEBOUNCE_SECONDS = 30
DEBOUNCE_GRACE_SECONDS = 120
BATCH_SIZE = 1000
MAX_BACKOFF_SECONDS = 3600
# Meta: "too many catalog batch requests" (new catalogs allow about 8 calls a minute).
CATALOG_RATE_LIMIT_CODE = 80014
REVIEW_POLL_SECONDS = 10 * 60
MAX_POLLED_BATCHES = 500
MAX_PRODUCT_PAGES = 100
MAX_STORED_ERRORS = 100
STALE_BATCH_AFTER = timedelta(hours=24)
REVIEW_STATUSES = frozenset({"pending", "approved", "rejected", "outdated"})
CONNECTED_WABA_STATUSES = (
    WhatsAppBusinessAccount.Status.ACTIVE,
    WhatsAppBusinessAccount.Status.RESTRICTED,
)

SyncStatus = Product.SyncStatus
ReviewStatus = Product.ReviewStatus
BatchStatus = CatalogSyncBatch.Status


class SyncBlocked(Exception):
    """The catalog can't be synced until the seller fixes something (the message says what)."""


def debounce_key(meta_catalog_id) -> str:
    return f"catalog:sync:{meta_catalog_id}"


def _connected_catalog_ids(workspace_id) -> list:
    return list(
        MetaCatalog.objects.filter(
            workspace_id=workspace_id, status=MetaCatalog.Status.CONNECTED
        ).values_list("pk", flat=True)
    )


def queue_sync(workspace_id) -> None:
    """Queue a debounced ``catalog.sync_products`` for each connected catalog, on commit."""
    from .tasks import sync_products

    for pk in _connected_catalog_ids(workspace_id):
        if cache.add(debounce_key(pk), 1, timeout=SYNC_DEBOUNCE_SECONDS + DEBOUNCE_GRACE_SECONDS):
            transaction.on_commit(
                partial(sync_products.apply_async, args=[str(pk)], countdown=SYNC_DEBOUNCE_SECONDS)
            )


def queue_delete(workspace_id, retailer_ids) -> None:
    """Queue Meta deletes for products about to be deleted locally (not debounced)."""
    from .tasks import sync_products

    retailer_ids = sorted(set(retailer_ids))
    if not retailer_ids:
        return
    for pk in _connected_catalog_ids(workspace_id):
        transaction.on_commit(
            partial(
                sync_products.apply_async,
                args=[str(pk)],
                kwargs={"delete_retailer_ids": retailer_ids},
            )
        )


def queue_full_sync(meta_catalog: MetaCatalog) -> None:
    from .tasks import sync_products

    transaction.on_commit(
        partial(sync_products.apply_async, args=[str(meta_catalog.pk)], kwargs={"full": True})
    )


def notify(meta_catalog: MetaCatalog, status: str) -> None:
    broadcast(
        meta_catalog.workspace_id,
        SYNC_FRAME,
        {"meta_catalog_id": str(meta_catalog.pk), "status": status},
    )


def is_rate_limited(exc: GraphAPIError) -> bool:
    return exc.code == CATALOG_RATE_LIMIT_CODE or isinstance(exc, RateLimitedError)


def backoff_seconds(retries: int, exc: GraphAPIError) -> int:
    if exc.retry_after:
        return min(exc.retry_after, MAX_BACKOFF_SECONDS)
    return min(60 * 2**retries, MAX_BACKOFF_SECONDS)


def waba_can_sync(waba: WhatsAppBusinessAccount) -> bool:
    return waba.status in CONNECTED_WABA_STATUSES and bool(waba.access_token)


def record_failure(meta_catalog: MetaCatalog, error: GraphAPIError | str) -> None:
    """Store why the sync failed (never the token) and tell the dashboard."""
    fields: dict = {}
    if isinstance(error, GraphAPIError):
        message = error.message or "Meta rejected the catalog sync."
        if isinstance(error, GraphPermissionError | TokenInvalidError):
            fields["status"] = MetaCatalog.Status.PERMISSIONS_MISSING
            message = "Reconnect WhatsApp to grant catalog permissions."
        logger.warning(
            "Catalog sync failed for catalog %s: %s (code=%s)",
            meta_catalog.catalog_id,
            type(error).__name__,
            error.code,
        )
    else:
        message = error
    fields["last_sync_error"] = message[:1000]
    MetaCatalog.objects.filter(pk=meta_catalog.pk).update(**fields)
    notify(meta_catalog, SyncStatus.FAILED)


def store_link(meta_catalog: MetaCatalog) -> str | None:
    """``https://wa.me/<digits>?text=Hi`` for the catalog WABA's number (the default first)."""
    numbers = (
        PhoneNumber.objects.filter(
            workspace_id=meta_catalog.workspace_id, waba_id=meta_catalog.waba_id
        )
        .exclude(registration_status=PhoneNumber.RegistrationStatus.DEREGISTERED)
        .order_by("-is_default", "created_at", "pk")
    )
    for number in numbers:
        digits = re.sub(r"\D", "", number.phone_e164 or number.display_phone_number)
        if digits:
            return f"https://wa.me/{digits}?text=Hi"
    return None


def format_price(paise: int) -> str:
    return f"{paise // 100}.{paise % 100:02d} INR"


def item_data(product: Product, *, link: str, brand: str) -> dict:
    data = {
        "id": product.sku,
        "title": product.name,
        "description": product.description or product.name,
        "availability": (
            "in stock"
            if product.buyer_availability == Product.Availability.IN_STOCK
            else "out of stock"
        ),
        "condition": "new",
        "price": format_price(product.price_paise),
        "link": link,
        "image_link": public_image_url(product),
        "brand": brand[:100] or product.name[:100],
    }
    if product.sale_price_paise is not None and product.sale_price_paise < product.price_paise:
        data["sale_price"] = format_price(product.sale_price_paise)
    return data


def _eligible(product: Product) -> bool:
    return product.is_active and bool(product.image)


def _validation_errors(response: dict) -> dict[str, str]:
    errors = {}
    for entry in response.get("validation_status") or []:
        if not isinstance(entry, dict) or not entry.get("errors"):
            continue
        messages = [
            str(error.get("message") or "")
            for error in entry["errors"]
            if isinstance(error, dict) and error.get("message")
        ]
        errors[str(entry.get("retailer_id", ""))] = "; ".join(messages) or "Meta rejected it."
    return errors


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def run_sync(
    meta_catalog: MetaCatalog, *, full: bool = False, delete_retailer_ids=()
) -> CatalogSyncBatch | None:
    """Send the catalog's changed products to Meta; returns the last batch recorded.

    Raises ``GraphAPIError`` (the task retries rate limits) or :class:`SyncBlocked`. Batches that
    were sent before an error stay recorded; the watermark only moves once everything is sent.
    """
    started = timezone.now()
    workspace_id = meta_catalog.workspace_id
    products = Product.objects.filter(workspace_id=workspace_id)
    changed = products
    if not full and meta_catalog.last_synced_at is not None:
        changed = products.filter(updated_at__gt=meta_catalog.last_synced_at)

    upserts = list(
        changed.filter(is_active=True).exclude(image="").order_by("position", "name", "pk")
    )
    removed = changed.filter(Q(is_active=False) | Q(image="")).exclude(
        meta_sync_status=SyncStatus.NOT_SYNCED, meta_product_id=""
    )
    delete_ids = set(delete_retailer_ids) | set(removed.values_list("sku", flat=True))
    if delete_ids:
        # A deleted SKU may have been reused by a product that is still sold.
        delete_ids -= set(
            products.filter(sku__in=delete_ids, is_active=True)
            .exclude(image="")
            .values_list("sku", flat=True)
        )

    requests: list[dict] = []
    if upserts:
        link = store_link(meta_catalog)
        if link is None:
            raise SyncBlocked("Add a WhatsApp number to this account to sync the catalog.")
        brand = meta_catalog.workspace.name
        requests += [
            {"method": "UPDATE", "data": item_data(product, link=link, brand=brand)}
            for product in upserts
        ]
    requests += [{"method": "DELETE", "data": {"id": sku}} for sku in sorted(delete_ids)]

    batch = None
    if requests:
        client = get_client(meta_catalog.waba.access_token)
        upsert_ids = {product.sku for product in upserts}
        for chunk in _chunks(requests, BATCH_SIZE):
            response = client.batch_catalog_items(meta_catalog.catalog_id, chunk)
            batch = _record_batch(meta_catalog, chunk, response, upsert_ids)

    MetaCatalog.objects.filter(pk=meta_catalog.pk).update(
        last_synced_at=started, last_sync_error=""
    )
    meta_catalog.last_synced_at = started
    if batch is not None:
        notify(meta_catalog, SyncStatus.PENDING if batch.handle else SyncStatus.FAILED)
    return batch


def _record_batch(
    meta_catalog: MetaCatalog, chunk: list[dict], response: dict, upsert_ids: set[str]
) -> CatalogSyncBatch:
    retailer_ids = [str(request["data"]["id"]) for request in chunk]
    handles = [handle for handle in response.get("handles") or [] if isinstance(handle, str)]
    rejected = _validation_errors(response)
    now = timezone.now()
    with transaction.atomic():
        batch = CatalogSyncBatch.objects.create(
            workspace_id=meta_catalog.workspace_id,
            meta_catalog=meta_catalog,
            handle=handles[0] if handles else "",
            status=BatchStatus.PENDING if handles else BatchStatus.FAILED,
            retailer_ids=retailer_ids,
            errors=[
                {"id": retailer_id, "message": message}
                for retailer_id, message in list(rejected.items())[:MAX_STORED_ERRORS]
            ],
            finished_at=None if handles else now,
        )
        products = Product.objects.filter(workspace_id=meta_catalog.workspace_id)
        sent = [sku for sku in retailer_ids if sku in upsert_ids]
        if not handles:
            products.filter(sku__in=sent).update(
                meta_sync_status=SyncStatus.FAILED,
                meta_sync_error="Meta did not accept the catalog update.",
            )
            return batch
        accepted = [sku for sku in sent if sku not in rejected]
        products.filter(sku__in=accepted).update(
            meta_sync_status=SyncStatus.PENDING, meta_sync_error=""
        )
        for sku in sent:
            if sku in rejected:
                products.filter(sku=sku).update(
                    meta_sync_status=SyncStatus.FAILED, meta_sync_error=rejected[sku][:1000]
                )
    return batch


# --- Polling ----------------------------------------------------------------------------------


def poll_pending_batches() -> None:
    """Finish pending batches and refresh review statuses (``catalog.poll_sync_status``)."""
    batches = (
        CatalogSyncBatch.objects.filter(status=BatchStatus.PENDING)
        .exclude(handle="")
        .select_related("meta_catalog__waba")
        .order_by("created_at")[:MAX_POLLED_BATCHES]
    )
    by_catalog: dict = defaultdict(list)
    catalogs: dict = {}
    for batch in batches:
        by_catalog[batch.meta_catalog_id].append(batch)
        catalogs[batch.meta_catalog_id] = batch.meta_catalog

    for catalog_pk, catalog_batches in by_catalog.items():
        _poll_catalog(catalogs[catalog_pk], catalog_batches)

    # Review happens after a batch finishes and can take hours: keep polling products under review.
    in_review = Product.objects.filter(
        meta_sync_status=SyncStatus.SYNCED,
        meta_review_status__in=(ReviewStatus.NONE, ReviewStatus.PENDING),
    ).values("workspace_id")
    reviewing = (
        MetaCatalog.objects.filter(status=MetaCatalog.Status.CONNECTED, workspace_id__in=in_review)
        .exclude(pk__in=list(by_catalog))
        .select_related("waba")
    )
    for meta_catalog in reviewing:
        if waba_can_sync(meta_catalog.waba) and cache.add(
            f"catalog:reviews:{meta_catalog.pk}", 1, timeout=REVIEW_POLL_SECONDS
        ):
            _refresh_reviews_safely(meta_catalog)


def _poll_catalog(meta_catalog: MetaCatalog, batches: list[CatalogSyncBatch]) -> None:
    now = timezone.now()
    if not waba_can_sync(meta_catalog.waba):
        for batch in batches:
            if now - batch.created_at > STALE_BATCH_AFTER:
                _finish_batch(batch, BatchStatus.FAILED, [{"message": "WhatsApp disconnected."}])
        return
    client = get_client(meta_catalog.waba.access_token)
    finished = False
    for batch in batches:
        try:
            response = client.get_catalog_batch_status(meta_catalog.catalog_id, batch.handle)
        except GraphAPIError as exc:
            if exc.retryable:
                continue
            _finish_batch(batch, BatchStatus.FAILED, [{"message": exc.message}])
            finished = True
            continue
        entries = response.get("data") or [{}]
        entry = entries[0] if isinstance(entries[0], dict) else {}
        status = str(entry.get("status") or "").lower()
        errors = [error for error in entry.get("errors") or [] if isinstance(error, dict)]
        if status == "finished":
            _finish_batch(batch, BatchStatus.FINISHED, errors)
            finished = True
        elif status == "error":
            _finish_batch(batch, BatchStatus.FAILED, errors or [{"message": "Meta failed it."}])
            finished = True
        elif now - batch.created_at > STALE_BATCH_AFTER:
            _finish_batch(batch, BatchStatus.FAILED, [{"message": "Meta did not finish it."}])
            finished = True
        else:
            batch.last_checked_at = now
            batch.save(update_fields=["last_checked_at", "updated_at"])

    if not finished:
        return
    _refresh_reviews_safely(meta_catalog, client)
    if CatalogSyncBatch.objects.filter(
        meta_catalog=meta_catalog, status=BatchStatus.PENDING
    ).exists():
        return
    failed = Product.objects.filter(
        workspace_id=meta_catalog.workspace_id, meta_sync_status=SyncStatus.FAILED
    ).count()
    MetaCatalog.objects.filter(pk=meta_catalog.pk).update(
        last_sync_error=f"{failed} product(s) could not be synced to Meta." if failed else ""
    )
    notify(meta_catalog, SyncStatus.FAILED if failed else SyncStatus.SYNCED)


def _finish_batch(batch: CatalogSyncBatch, status: str, errors: list[dict]) -> None:
    now = timezone.now()
    messages = {
        str(error["id"]): str(error.get("message") or "Meta rejected this product.")
        for error in errors
        if error.get("id")
    }
    batch_message = next(
        (str(error.get("message")) for error in errors if error.get("message")), ""
    )
    with transaction.atomic():
        products = Product.objects.filter(
            workspace_id=batch.workspace_id, sku__in=batch.retailer_ids
        ).only("pk", "sku", "is_active", "image", "meta_sync_status", "meta_product_id")
        synced, reset = [], []
        for product in products:
            if not _eligible(product):
                if product.meta_sync_status != SyncStatus.NOT_SYNCED or product.meta_product_id:
                    reset.append(product.pk)
            elif product.sku in messages or (
                status == BatchStatus.FAILED and product.meta_sync_status == SyncStatus.PENDING
            ):
                Product.objects.filter(pk=product.pk).update(
                    meta_sync_status=SyncStatus.FAILED,
                    meta_sync_error=(messages.get(product.sku) or batch_message)[:1000],
                )
            elif product.meta_sync_status == SyncStatus.PENDING:
                synced.append(product.pk)
        Product.objects.filter(pk__in=synced).update(
            meta_sync_status=SyncStatus.SYNCED, meta_synced_at=now, meta_sync_error=""
        )
        Product.objects.filter(pk__in=reset).update(
            meta_sync_status=SyncStatus.NOT_SYNCED,
            meta_review_status=ReviewStatus.NONE,
            meta_rejection_reasons=[],
            meta_product_id="",
            meta_synced_at=None,
            meta_sync_error="",
        )
        batch.status = status
        batch.errors = errors[:MAX_STORED_ERRORS]
        batch.finished_at = batch.last_checked_at = now
        batch.save(
            update_fields=["status", "errors", "finished_at", "last_checked_at", "updated_at"]
        )


def _refresh_reviews_safely(meta_catalog: MetaCatalog, client=None) -> None:
    try:
        refresh_reviews(meta_catalog, client)
    except GraphAPIError as exc:
        logger.warning(
            "Catalog review refresh failed for catalog %s: %s",
            meta_catalog.catalog_id,
            type(exc).__name__,
        )


def refresh_reviews(meta_catalog: MetaCatalog, client=None) -> None:
    """Copy Meta's product id, review status and rejection reasons onto synced products."""
    client = client or get_client(meta_catalog.waba.access_token)
    found: dict[str, tuple[str, str, list[str]]] = {}
    after = None
    for _ in range(MAX_PRODUCT_PAGES):
        page = client.list_catalog_products(meta_catalog.catalog_id, after=after, limit=100)
        for item in page.get("data") or []:
            if not isinstance(item, dict) or not item.get("retailer_id"):
                continue
            review = str(item.get("review_status") or "").lower()
            reasons = [str(reason) for reason in item.get("review_rejection_reasons") or []]
            found[str(item["retailer_id"])] = (
                str(item.get("id") or ""),
                review if review in REVIEW_STATUSES else ReviewStatus.NONE,
                reasons,
            )
        paging = page.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not after:
            break

    skus = list(found)
    for chunk in _chunks(skus, BATCH_SIZE):
        products = Product.objects.filter(
            workspace_id=meta_catalog.workspace_id, sku__in=chunk
        ).only("pk", "sku", "meta_product_id", "meta_review_status", "meta_rejection_reasons")
        for product in products:
            meta_id, review, reasons = found[product.sku]
            current = (product.meta_product_id, product.meta_review_status)
            if current == (meta_id, review) and product.meta_rejection_reasons == reasons:
                continue
            Product.objects.filter(pk=product.pk).update(
                meta_product_id=meta_id, meta_review_status=review, meta_rejection_reasons=reasons
            )
