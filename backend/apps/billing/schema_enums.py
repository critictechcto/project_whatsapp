"""Contract enum names for billing (docs/contracts/wave-2.md, billing-cashfree.md). Values only;
no model imports."""

SUBSCRIPTION_STATUSES = ("trialing", "pending", "active", "halted", "cancelled", "expired")
BILLING_INTERVALS = ("monthly", "annual")
INVOICE_STATUSES = ("issued", "paid", "void")
CASHFREE_MODES = ("sandbox", "production")
# Same values as payments' PaymentProviderEnum, so the schema reuses that component.
BILLING_PROVIDERS = ("razorpay", "cashfree")
PAYMENT_MODES = ("autopay", "one_time")

ENUM_NAME_OVERRIDES = {
    "BillingPaymentModeEnum": PAYMENT_MODES,
    "SubscriptionStatusEnum": SUBSCRIPTION_STATUSES,
    "BillingIntervalEnum": BILLING_INTERVALS,
    "InvoiceStatusEnum": INVOICE_STATUSES,
    "CashfreeModeEnum": CASHFREE_MODES,
}
