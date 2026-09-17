"""Contract enum names for analytics (docs/contracts/analytics.md). No model imports.

Both value sets overlap enums of other apps, so they carry their own labels: drf-spectacular keys
overrides on (value, label) pairs, and a second override with the same pairs as ``orders``'
``PaymentMethodEnum`` would be a duplicate.
"""

# Outbound message sources: inbox's MessageSourceEnum without ``inbound``.
MESSAGE_SOURCES = (
    ("inbox", "Inbox"),
    ("campaign", "Campaign"),
    ("automation", "Automation"),
    ("api", "API"),
    ("commerce", "Commerce"),
)
# Blank (no method chosen yet) is allowed on the field itself.
PAYMENT_METHODS = (
    ("online", "Online payment"),
    ("cod", "Cash on delivery (COD)"),
)
REPORTS = ("messages", "templates", "campaigns", "team", "commerce")

ENUM_NAME_OVERRIDES = {
    "AnalyticsMessageSourceEnum": MESSAGE_SOURCES,
    "AnalyticsPaymentMethodEnum": PAYMENT_METHODS,
}
