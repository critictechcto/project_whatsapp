"""Catalog: the seller's products and collections, and the Meta catalog they sync to.

Money is integer paise (GST included). ``Product.sku`` is Meta's ``retailer_id``: unique per
workspace and read-only after create. ``stock_qty`` null means stock is not tracked; a tracked
stock of 0 makes buyers see the product as out of stock whatever ``availability`` says.
"""

import hashlib
from pathlib import PurePosixPath

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from common.models import TenantScopedModel

CURRENCY = "INR"
MIN_PRICE_PAISE = 100
DEFAULT_MAX_QTY_PER_ORDER = 10
MAX_QTY_PER_ORDER = 99

sku_validator = RegexValidator(
    r"^[A-Za-z0-9_-]{1,100}$", "Use 1-100 letters, digits, underscores or hyphens."
)


def _content_sha256(field_file) -> str:
    """SHA-256 of an uploaded file's content, leaving the read position at the start."""
    hasher = hashlib.sha256()
    content = field_file.file if hasattr(field_file, "file") else field_file
    if hasattr(content, "seek"):
        content.seek(0)
    if hasattr(content, "chunks"):
        for chunk in content.chunks():
            hasher.update(chunk)
    else:
        for chunk in iter(lambda: content.read(64 * 1024), b""):
            hasher.update(chunk)
    if hasattr(content, "seek"):
        content.seek(0)
    return hasher.hexdigest()


def product_image_path(instance: "Product", filename: str) -> str:
    """``catalog/products/<workspace>/<aa>/<sha256>.<ext>``: a new image gets a new URL, so Meta
    and WhatsApp clients never show a stale cached image."""
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix not in {".jpg", ".png"}:
        suffix = ".jpg"
    digest = _content_sha256(instance.image)
    return f"catalog/products/{instance.workspace_id}/{digest[:2]}/{digest}{suffix}"


class Collection(TenantScopedModel):
    """A group of products shown as one bot list row (name ≤ 24, description ≤ 72)."""

    name = models.CharField(max_length=24)
    description = models.CharField(max_length=72, blank=True)
    position = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ("position", "name")
        constraints = [
            models.UniqueConstraint(
                Lower("name"), F("workspace"), name="catalog_collection_unique_name_ci"
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "position"], name="catalog_coll_ws_position_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class Product(TenantScopedModel):
    class Availability(models.TextChoices):
        IN_STOCK = "in_stock", "In stock"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"

    class SyncStatus(models.TextChoices):
        NOT_SYNCED = "not_synced", "Not synced"
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    class ReviewStatus(models.TextChoices):
        NONE = "none", "None"
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        OUTDATED = "outdated", "Outdated"

    sku = models.CharField(max_length=100, validators=[sku_validator])
    name = models.CharField(max_length=200)
    description = models.TextField(max_length=1000, blank=True)
    price_paise = models.PositiveIntegerField(validators=[MinValueValidator(MIN_PRICE_PAISE)])
    sale_price_paise = models.PositiveIntegerField(null=True, blank=True)
    collection = models.ForeignKey(
        Collection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    availability = models.CharField(
        max_length=16, choices=Availability.choices, default=Availability.IN_STOCK
    )
    stock_qty = models.PositiveIntegerField(null=True, blank=True)
    max_qty_per_order = models.PositiveSmallIntegerField(
        default=DEFAULT_MAX_QTY_PER_ORDER,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_QTY_PER_ORDER)],
    )
    position = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    image = models.FileField(upload_to=product_image_path, max_length=255, blank=True)

    # Meta catalog sync (catalog.sync_products / catalog.poll_sync_status).
    meta_sync_status = models.CharField(
        max_length=16, choices=SyncStatus.choices, default=SyncStatus.NOT_SYNCED
    )
    meta_review_status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.NONE
    )
    meta_rejection_reasons = models.JSONField(default=list, blank=True)
    meta_product_id = models.CharField(max_length=64, blank=True)
    meta_synced_at = models.DateTimeField(null=True, blank=True)
    meta_sync_error = models.TextField(blank=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ("position", "name")
        constraints = [
            models.UniqueConstraint(fields=["workspace", "sku"], name="catalog_product_unique_sku"),
            models.CheckConstraint(
                condition=Q(price_paise__gte=MIN_PRICE_PAISE),
                name="catalog_product_min_price",
            ),
            models.CheckConstraint(
                condition=Q(sale_price_paise__isnull=True)
                | Q(sale_price_paise__lt=F("price_paise")),
                name="catalog_product_sale_below_price",
            ),
            models.CheckConstraint(
                condition=Q(max_qty_per_order__gte=1) & Q(max_qty_per_order__lte=MAX_QTY_PER_ORDER),
                name="catalog_product_max_qty_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "position", "name"], name="catalog_prod_ws_position_idx"
            ),
            models.Index(fields=["workspace", "collection"], name="catalog_prod_ws_coll_idx"),
            models.Index(
                fields=["workspace", "is_active", "availability"],
                name="catalog_prod_ws_active_idx",
            ),
            models.Index(
                fields=["workspace", "meta_review_status"], name="catalog_prod_ws_review_idx"
            ),
            models.Index(fields=["workspace", "meta_sync_status"], name="catalog_prod_ws_sync_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"

    @property
    def currency(self) -> str:
        return CURRENCY

    @property
    def effective_price_paise(self) -> int:
        if self.sale_price_paise is not None and self.sale_price_paise < self.price_paise:
            return self.sale_price_paise
        return self.price_paise

    @property
    def is_stock_tracked(self) -> bool:
        return self.stock_qty is not None

    @property
    def buyer_availability(self) -> str:
        """What buyers see: out of stock when the seller says so or tracked stock is 0."""
        if self.availability == self.Availability.OUT_OF_STOCK or self.stock_qty == 0:
            return self.Availability.OUT_OF_STOCK
        return self.Availability.IN_STOCK


class MetaCatalog(TenantScopedModel):
    """The Meta commerce catalog connected to a WABA (at most one per WABA)."""

    class Status(models.TextChoices):
        CONNECTED = "connected", "Connected"
        PERMISSIONS_MISSING = "permissions_missing", "Permissions missing"
        ERROR = "error", "Error"

    waba = models.OneToOneField(
        "whatsapp.WhatsAppBusinessAccount", on_delete=models.CASCADE, related_name="meta_catalog"
    )
    catalog_id = models.CharField(max_length=64, db_index=True)
    catalog_name = models.CharField(max_length=255, blank=True)
    business_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CONNECTED)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["workspace", "status"], name="catalog_meta_ws_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.catalog_name or self.catalog_id} ({self.status})"


class MetaCatalogPhoneSetting(TenantScopedModel):
    """Meta commerce settings of one business number: cart on/off and catalog visibility."""

    meta_catalog = models.ForeignKey(
        MetaCatalog, on_delete=models.CASCADE, related_name="phone_settings"
    )
    phone_number = models.OneToOneField(
        "whatsapp.PhoneNumber", on_delete=models.CASCADE, related_name="commerce_setting"
    )
    is_cart_enabled = models.BooleanField(default=False)
    is_catalog_visible = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        pass

    def __str__(self) -> str:
        return f"Commerce settings for {self.phone_number_id}"


class CatalogSyncBatch(TenantScopedModel):
    """One Meta ``items_batch`` request; polled until Meta reports it finished."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        FINISHED = "finished", "Finished"
        FAILED = "failed", "Failed"

    meta_catalog = models.ForeignKey(
        MetaCatalog, on_delete=models.CASCADE, related_name="sync_batches"
    )
    handle = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Retailer ids (SKUs) sent in the batch, so polling can update those products.
    retailer_ids = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["status", "created_at"], name="catalog_batch_status_idx"),
        ]

    def __str__(self) -> str:
        return f"Catalog batch {self.handle or self.pk} ({self.status})"
