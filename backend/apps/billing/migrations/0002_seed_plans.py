"""Seed the default plan catalogue (prices in paise before GST; annual = 10 x monthly).

A frozen copy of ``apps.billing.plans.DEFAULT_PLANS`` so later catalogue edits don't rewrite
history. A test checks the two stay in sync.
"""

from django.db import migrations

_ALL_FEATURES = ["scheduled_campaigns", "keyword_automations", "api_access"]

PLANS = {
    "starter": {
        "name": "Starter",
        "monthly_price_paise": 99900,
        "annual_price_paise": 999000,
        "limits": {"whatsapp_numbers": 1, "members": 2, "contacts": 5000},
        "features": [],
        "is_active": True,
        "sort_order": 10,
    },
    "growth": {
        "name": "Growth",
        "monthly_price_paise": 249900,
        "annual_price_paise": 2499000,
        "limits": {"whatsapp_numbers": 2, "members": 5, "contacts": 25000},
        "features": _ALL_FEATURES,
        "is_active": True,
        "sort_order": 20,
    },
    "pro": {
        "name": "Pro",
        "monthly_price_paise": 599900,
        "annual_price_paise": 5999000,
        "limits": {"whatsapp_numbers": 5, "members": 15, "contacts": 100000},
        "features": _ALL_FEATURES,
        "is_active": True,
        "sort_order": 30,
    },
}


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for slug, fields in PLANS.items():
        Plan.objects.get_or_create(
            slug=slug, defaults={**fields, "limits": dict(fields["limits"]), "features": list(fields["features"])}
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [migrations.RunPython(seed_plans, migrations.RunPython.noop)]
