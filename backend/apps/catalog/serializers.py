"""Catalog API shapes (docs/contracts/wave-3-commerce.md). ``FooSerializer`` produces ``Foo``."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import services
from .models import MAX_QTY_PER_ORDER, MIN_PRICE_PAISE
from .schema_enums import (
    CATALOG_SYNC_STATUSES,
    META_CATALOG_STATUSES,
    META_REVIEW_STATUSES,
    PRODUCT_AVAILABILITIES,
)

SKU_PATTERN = r"^[A-Za-z0-9_-]{1,100}$"
MAX_REORDER_IDS = 5000

# --- Products -------------------------------------------------------------------------------


class CollectionRefSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class ProductSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    sku = serializers.CharField(read_only=True, help_text="Meta retailer_id; read-only.")
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    price_paise = serializers.IntegerField(read_only=True)
    sale_price_paise = serializers.IntegerField(read_only=True, allow_null=True)
    effective_price_paise = serializers.IntegerField(read_only=True)
    currency = serializers.CharField(read_only=True, help_text="Always INR.")
    image_url = serializers.SerializerMethodField()
    collection = CollectionRefSerializer(read_only=True, allow_null=True)
    availability = serializers.ChoiceField(choices=PRODUCT_AVAILABILITIES, read_only=True)
    stock_qty = serializers.IntegerField(
        read_only=True, allow_null=True, help_text="Null means stock is not tracked."
    )
    max_qty_per_order = serializers.IntegerField(read_only=True)
    position = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    meta_sync_status = serializers.ChoiceField(choices=CATALOG_SYNC_STATUSES, read_only=True)
    meta_review_status = serializers.ChoiceField(choices=META_REVIEW_STATUSES, read_only=True)
    meta_rejection_reasons = serializers.ListField(child=serializers.CharField(), read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    @extend_schema_field(serializers.URLField(allow_null=True, read_only=True))
    def get_image_url(self, product) -> str | None:
        return services.public_image_url(product)


class ProductWriteSerializer(serializers.Serializer):
    """Create or PATCH a product. ``sku`` is accepted on create only."""

    sku = serializers.RegexField(SKU_PATTERN, max_length=100, help_text="Create only.")
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    price_paise = serializers.IntegerField(min_value=MIN_PRICE_PAISE)
    sale_price_paise = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    availability = serializers.ChoiceField(choices=PRODUCT_AVAILABILITIES, required=False)
    stock_qty = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    max_qty_per_order = serializers.IntegerField(
        min_value=1, max_value=MAX_QTY_PER_ORDER, required=False
    )
    position = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        price = attrs.get("price_paise")
        sale = attrs.get("sale_price_paise")
        if price is not None and sale is not None and sale >= price:
            raise serializers.ValidationError(
                {"sale_price_paise": ["The sale price must be lower than the price."]}
            )
        return attrs


class ProductImageUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="JPEG or PNG, at most 8 MB, at least 500x500 px.")


class ProductImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="CSV, at most 2 MB and 5,000 rows.")


class ProductImportRowErrorSerializer(serializers.Serializer):
    row = serializers.IntegerField(read_only=True)
    sku = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True)


class ProductImportResultSerializer(serializers.Serializer):
    created_count = serializers.IntegerField(read_only=True)
    updated_count = serializers.IntegerField(read_only=True)
    skipped_count = serializers.IntegerField(read_only=True)
    errors = ProductImportRowErrorSerializer(many=True, read_only=True)


class ReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        max_length=MAX_REORDER_IDS,
        help_text="The full ordering; positions are rewritten 0..n.",
    )


# --- Collections ----------------------------------------------------------------------------


class CollectionSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    position = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    product_count = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CollectionWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=24, help_text="Shown as a list row title.")
    description = serializers.CharField(max_length=72, required=False, allow_blank=True)
    position = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)


# --- Meta catalogs --------------------------------------------------------------------------


class MetaCatalogWabaSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    waba_id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)


class MetaCatalogCountsSerializer(serializers.Serializer):
    synced = serializers.IntegerField(read_only=True)
    pending = serializers.IntegerField(read_only=True)
    failed = serializers.IntegerField(read_only=True)
    approved = serializers.IntegerField(read_only=True)
    rejected = serializers.IntegerField(read_only=True)


class CommerceSettingsSerializer(serializers.Serializer):
    """Per-number cart and catalog visibility. As a PATCH body only ``phone_number_id`` and the
    booleans are read."""

    phone_number_id = serializers.UUIDField()
    display_phone_number = serializers.CharField(read_only=True)
    is_cart_enabled = serializers.BooleanField(required=False)
    is_catalog_visible = serializers.BooleanField(required=False)


class MetaCatalogSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    waba = MetaCatalogWabaSerializer(read_only=True)
    catalog_id = serializers.CharField(read_only=True)
    catalog_name = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=META_CATALOG_STATUSES, read_only=True)
    last_synced_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_sync_error = serializers.CharField(read_only=True)
    product_counts = serializers.SerializerMethodField()
    phone_numbers = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    @extend_schema_field(MetaCatalogCountsSerializer)
    def get_product_counts(self, meta_catalog) -> dict:
        return services.meta_catalog_product_counts(meta_catalog)

    @extend_schema_field(CommerceSettingsSerializer(many=True))
    def get_phone_numbers(self, meta_catalog) -> list[dict]:
        return CommerceSettingsSerializer(
            services.meta_catalog_phone_settings(meta_catalog), many=True
        ).data


class AvailableCatalogSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True, help_text="Meta catalog id.")
    name = serializers.CharField(read_only=True)


class MetaCatalogConnectSerializer(serializers.Serializer):
    """Connect an existing catalog (``catalog_id``) or create one (``create_name``)."""

    waba_id = serializers.UUIDField(help_text="Id of the WhatsAppBusinessAccount.")
    catalog_id = serializers.RegexField(r"^[0-9]{1,64}$", required=False)
    create_name = serializers.CharField(max_length=100, required=False)

    def validate(self, attrs: dict) -> dict:
        if bool(attrs.get("catalog_id")) == bool(attrs.get("create_name")):
            raise serializers.ValidationError(
                {"non_field_errors": ["Send exactly one of catalog_id or create_name."]}
            )
        return attrs
