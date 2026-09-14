"""Contract enum names for automations (docs/contracts/wave-2.md). Values only; no model imports."""

AUTOMATION_TRIGGERS = ("keyword", "first_inbound", "new_contact", "outside_business_hours")
KEYWORD_MATCHES = ("exact", "contains")
AUTOMATION_ACTION_TYPES = (
    "send_text",
    "send_template",
    "add_tags",
    "assign",
    "close_conversation",
    "send_shop_menu",
    "send_catalog",
    "send_collection",
)
AUTOMATION_RUN_STATUSES = ("succeeded", "skipped", "failed")

ENUM_NAME_OVERRIDES = {
    "AutomationTriggerEnum": AUTOMATION_TRIGGERS,
    "KeywordMatchEnum": KEYWORD_MATCHES,
    "AutomationActionTypeEnum": AUTOMATION_ACTION_TYPES,
    "AutomationRunStatusEnum": AUTOMATION_RUN_STATUSES,
}
