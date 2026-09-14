"""Contract enum names for the catalog (docs/contracts/wave-3-commerce.md). Values only."""

PRODUCT_AVAILABILITIES = ("in_stock", "out_of_stock")
CATALOG_SYNC_STATUSES = ("not_synced", "pending", "synced", "failed")
META_REVIEW_STATUSES = ("none", "pending", "approved", "rejected", "outdated")
META_CATALOG_STATUSES = ("connected", "permissions_missing", "error")

ENUM_NAME_OVERRIDES = {
    "ProductAvailabilityEnum": PRODUCT_AVAILABILITIES,
    "CatalogSyncStatusEnum": CATALOG_SYNC_STATUSES,
    "MetaReviewStatusEnum": META_REVIEW_STATUSES,
    "MetaCatalogStatusEnum": META_CATALOG_STATUSES,
}
