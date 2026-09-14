"""Contract enum names for seller alerts (docs/contracts/wave-3-commerce.md). Values only."""

ALERT_RECIPIENT_STATUSES = ("pending", "verified", "opted_out")
ALERT_EVENTS = ("new_order", "needs_attention", "order_cancelled")

ENUM_NAME_OVERRIDES = {
    "AlertRecipientStatusEnum": ALERT_RECIPIENT_STATUSES,
    "AlertEventEnum": ALERT_EVENTS,
}
