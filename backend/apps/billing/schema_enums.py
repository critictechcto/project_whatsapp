"""Contract enum names for billing (docs/contracts/wave-2.md). Values only; no model imports."""

SUBSCRIPTION_STATUSES = ("trialing", "pending", "active", "halted", "cancelled", "expired")
BILLING_INTERVALS = ("monthly", "annual")
INVOICE_STATUSES = ("issued", "paid", "void")

ENUM_NAME_OVERRIDES = {
    "SubscriptionStatusEnum": SUBSCRIPTION_STATUSES,
    "BillingIntervalEnum": BILLING_INTERVALS,
    "InvoiceStatusEnum": INVOICE_STATUSES,
}
