"""Contract enum names for the catalog (docs/contracts/wave-3-commerce.md). Values only."""

PRODUCT_KINDS = ("product", "service")
PRODUCT_AVAILABILITIES = ("in_stock", "out_of_stock")
# docs/contracts/booking-payments.md
BOOKING_PAYMENTS = ("store_default", "advance", "full")
ADVANCE_TYPES = ("amount", "percent")
CATALOG_SYNC_STATUSES = ("not_synced", "pending", "synced", "failed")
META_REVIEW_STATUSES = ("none", "pending", "approved", "rejected", "outdated")
META_CATALOG_STATUSES = ("connected", "permissions_missing", "error")

ENUM_NAME_OVERRIDES = {
    "ProductKindEnum": PRODUCT_KINDS,
    "ProductAvailabilityEnum": PRODUCT_AVAILABILITIES,
    "BookingPaymentEnum": BOOKING_PAYMENTS,
    "AdvanceTypeEnum": ADVANCE_TYPES,
    "CatalogSyncStatusEnum": CATALOG_SYNC_STATUSES,
    "MetaReviewStatusEnum": META_REVIEW_STATUSES,
    "MetaCatalogStatusEnum": META_CATALOG_STATUSES,
}
