"""Contract enum names for offers (docs/contracts/services-and-offers.md). Values only."""

DISCOUNT_TYPES = ("none", "percent", "amount")
APPLIES_TO = ("all", "products", "services")
CLAIM_STATUSES = ("claimed", "applied", "redeemed", "expired")

ENUM_NAME_OVERRIDES = {
    "OfferDiscountTypeEnum": DISCOUNT_TYPES,
    "OfferAppliesToEnum": APPLIES_TO,
    "OfferClaimStatusEnum": CLAIM_STATUSES,
}
