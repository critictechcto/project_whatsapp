"""Seller-side product and collection writes. Each product change queues the Meta catalog sync."""

from django.db import IntegrityError, transaction
from django.db.models import Max
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from . import images, sync
from .models import Collection, Product

PRODUCT_FIELDS = (
    "name",
    "description",
    "price_paise",
    "sale_price_paise",
    "availability",
    "stock_qty",
    "max_qty_per_order",
    "position",
    "is_active",
)
COLLECTION_FIELDS = ("name", "description", "position", "is_active")


def sku_taken() -> serializers.ValidationError:
    return serializers.ValidationError(
        {"sku": [ErrorDetail("A product with this SKU already exists.", code="sku_taken")]}
    )


def _next_position(queryset) -> int:
    top = queryset.aggregate(top=Max("position"))["top"]
    return 0 if top is None else top + 1


def _collection(workspace, collection_id) -> Collection | None:
    if collection_id is None:
        return None
    collection = Collection.objects.filter(workspace=workspace, pk=collection_id).first()
    if collection is None:
        raise serializers.ValidationError({"collection_id": ["Collection not found."]})
    return collection


def _check_sale_price(product: Product) -> None:
    if product.sale_price_paise is not None and product.sale_price_paise >= product.price_paise:
        raise serializers.ValidationError(
            {"sale_price_paise": ["The sale price must be lower than the price."]}
        )


# --- Products ---------------------------------------------------------------------------------


def create_product(workspace, data: dict) -> Product:
    products = Product.objects.filter(workspace=workspace)
    if products.filter(sku=data["sku"]).exists():
        raise sku_taken()
    product = Product(
        workspace=workspace,
        sku=data["sku"],
        collection=_collection(workspace, data.get("collection_id")),
    )
    for name in PRODUCT_FIELDS:
        if name in data:
            setattr(product, name, data[name])
    if "position" not in data:
        product.position = _next_position(products)
    _check_sale_price(product)
    try:
        with transaction.atomic():
            product.save()
    except IntegrityError:
        raise sku_taken() from None
    sync.queue_sync(workspace.pk)
    return product


def update_product(product: Product, data: dict) -> Product:
    """PATCH: only the given fields are written, so concurrent stock reservations survive."""
    if "sku" in data and data["sku"] != product.sku:
        raise serializers.ValidationError(
            {"sku": ["The SKU can't be changed after the product is created."]}
        )
    changed = [name for name in PRODUCT_FIELDS if name in data]
    for name in changed:
        setattr(product, name, data[name])
    if "collection_id" in data:
        product.collection = _collection(product.workspace, data["collection_id"])
        changed.append("collection")
    _check_sale_price(product)
    product.save(update_fields=[*changed, "updated_at"])
    sync.queue_sync(product.workspace_id)
    return product


def delete_product(product: Product) -> None:
    """Queue the Meta delete (by SKU) on commit, then delete the row. Order items keep their
    snapshots."""
    with transaction.atomic():
        if product.meta_sync_status != Product.SyncStatus.NOT_SYNCED or product.meta_product_id:
            sync.queue_delete(product.workspace_id, [product.sku])
        product.delete()


def set_product_image(product: Product, upload) -> Product:
    suffix = images.validate_image(upload)
    product.image.name = images.store_image(product, upload, suffix)
    product.save(update_fields=["image", "updated_at"])
    sync.queue_sync(product.workspace_id)
    return product


def remove_product_image(product: Product) -> Product:
    if product.image:
        product.image = ""
        product.save(update_fields=["image", "updated_at"])
        sync.queue_sync(product.workspace_id)
    return product


# --- Collections ------------------------------------------------------------------------------


def _check_collection_name(workspace, name: str, *, exclude_pk=None) -> None:
    clash = Collection.objects.filter(workspace=workspace, name__iexact=name)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise serializers.ValidationError({"name": ["A collection with this name already exists."]})


def _save_collection(collection: Collection, **kwargs) -> None:
    try:
        with transaction.atomic():
            collection.save(**kwargs)
    except IntegrityError:
        raise serializers.ValidationError(
            {"name": ["A collection with this name already exists."]}
        ) from None


def create_collection(workspace, data: dict) -> Collection:
    _check_collection_name(workspace, data["name"])
    collection = Collection(workspace=workspace)
    for name in COLLECTION_FIELDS:
        if name in data:
            setattr(collection, name, data[name])
    if "position" not in data:
        collection.position = _next_position(Collection.objects.filter(workspace=workspace))
    _save_collection(collection)
    return collection


def update_collection(collection: Collection, data: dict) -> Collection:
    if "name" in data:
        _check_collection_name(collection.workspace, data["name"], exclude_pk=collection.pk)
    changed = [name for name in COLLECTION_FIELDS if name in data]
    for name in changed:
        setattr(collection, name, data[name])
    _save_collection(collection, update_fields=[*changed, "updated_at"])
    return collection


# --- Ordering ---------------------------------------------------------------------------------


def reorder(model, workspace, ids: list) -> None:
    """Rewrite positions: ``ids`` get 0..n-1 in order and any rows not listed follow in their
    current order. Positions aren't synced to Meta, so products aren't marked changed."""
    if len(set(ids)) != len(ids):
        raise serializers.ValidationError({"ids": ["Each id may appear only once."]})
    with transaction.atomic():
        rows = {
            row.pk: row
            for row in model.objects.select_for_update()
            .filter(workspace=workspace)
            .only("pk", "position", "name")
        }
        unknown = [str(pk) for pk in ids if pk not in rows]
        if unknown:
            raise serializers.ValidationError(
                {"ids": [f"Not found in this workspace: {', '.join(unknown[:10])}."]}
            )
        listed = set(ids)
        rest = sorted(
            (row for pk, row in rows.items() if pk not in listed),
            key=lambda row: (row.position, row.name, str(row.pk)),
        )
        changed = []
        for position, row in enumerate([rows[pk] for pk in ids] + rest):
            if row.position != position:
                row.position = position
                changed.append(row)
        model.objects.bulk_update(changed, ["position"], batch_size=500)
