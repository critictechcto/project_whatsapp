"""Contract enum names for campaigns (docs/contracts/wave-2.md). Values only; no model imports."""

CAMPAIGN_STATUSES = (
    "draft",
    "scheduled",
    "running",
    "paused",
    "completed",
    "cancelled",
    "failed",
)
RECIPIENT_STATUSES = ("pending", "skipped", "queued", "sent", "delivered", "read", "failed")
VARIABLE_SOURCE_TYPES = ("contact_field", "attribute", "static")
AUDIENCE_MATCHES = ("any", "all")

ENUM_NAME_OVERRIDES = {
    "CampaignStatusEnum": CAMPAIGN_STATUSES,
    "RecipientStatusEnum": RECIPIENT_STATUSES,
    "VariableSourceTypeEnum": VARIABLE_SOURCE_TYPES,
    "AudienceMatchEnum": AUDIENCE_MATCHES,
}
