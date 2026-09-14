"""Demo automations for ``manage.py seed_demo``. Safe to run repeatedly: existing rules (matched by
name) and a business-hours schedule someone already set are left untouched."""

from .models import AutomationRule, BusinessHours

DEMO_SCHEDULE = [{"day": day, "start": "10:00", "end": "19:00"} for day in range(6)]  # Mon-Sat

DEMO_RULES = [
    {
        "name": "Price enquiry reply",
        "trigger": AutomationRule.Trigger.KEYWORD,
        "keywords": ["price", "prices", "rate"],
        "keyword_match": AutomationRule.KeywordMatch.CONTAINS,
        "priority": 10,
        "cooldown_minutes": 60,
        "stop_processing": True,
        "actions": [
            {
                "type": "send_text",
                "config": {
                    "text": (
                        "Thanks for asking! Our plans start at ₹499 a month. "
                        "Reply with the product name and we'll share the exact price."
                    )
                },
            }
        ],
    },
    {
        "name": "Away message",
        "trigger": AutomationRule.Trigger.OUTSIDE_BUSINESS_HOURS,
        "priority": 20,
        "cooldown_minutes": 240,
        "stop_processing": True,
        "actions": [
            {
                "type": "send_text",
                "config": {
                    "text": (
                        "Thanks for your message. We're open Monday to Saturday, 10 AM to 7 PM, "
                        "and will reply as soon as we're back."
                    )
                },
            }
        ],
    },
    {
        "name": "Welcome message",
        "trigger": AutomationRule.Trigger.FIRST_INBOUND,
        "priority": 30,
        "actions": [
            {
                "type": "send_text",
                "config": {"text": "Hi! Welcome. A member of our team will be with you shortly."},
            }
        ],
    },
]


def seed(workspace) -> None:
    hours, _ = BusinessHours.objects.get_or_create(workspace=workspace)
    if not hours.schedule:
        hours.enabled = True
        hours.schedule = DEMO_SCHEDULE
        hours.save(update_fields=["enabled", "schedule", "updated_at"])

    for definition in DEMO_RULES:
        defaults = {key: value for key, value in definition.items() if key != "name"}
        AutomationRule.objects.get_or_create(
            workspace=workspace, name=definition["name"], defaults=defaults
        )
