"""Contract enum names for payments (docs/contracts/wave-3-commerce.md). Values only."""

PAYMENT_PROVIDERS = ("razorpay",)
PAYMENT_MODES = ("test", "live")
PAYMENT_ACCOUNT_STATUSES = ("not_configured", "unverified", "verified", "invalid")
PAYMENT_LINK_STATUSES = ("creating", "created", "paid", "expired", "cancelled", "failed")

ENUM_NAME_OVERRIDES = {
    "PaymentProviderEnum": PAYMENT_PROVIDERS,
    "PaymentModeEnum": PAYMENT_MODES,
    "PaymentAccountStatusEnum": PAYMENT_ACCOUNT_STATUSES,
    "PaymentLinkStatusEnum": PAYMENT_LINK_STATUSES,
}
