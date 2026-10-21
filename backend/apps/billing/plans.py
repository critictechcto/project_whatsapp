"""The default plan catalogue (names, limits, features). Prices come from Razorpay plans
(``apps.billing.prices``); the marketing copy in ``frontend/src/config/site.ts`` must match.

The data migration ``0002_seed_plans`` seeds the same values; :func:`ensure_default_plans`
re-creates missing rows (for example after a transactional test flushed the table) without
overwriting plans an admin has edited.
"""

TRIAL_PLAN_SLUG = "growth"
TRIAL_DAYS = 14

# Every plan includes the WhatsApp store (migration 0003 adds it to existing rows). Analytics is
# on Growth and Pro only (migration 0004 adds it to existing rows).
COMMERCE_FEATURE = "commerce"
ANALYTICS_FEATURE = "analytics"
_ALL_FEATURES = [
    "scheduled_campaigns",
    "keyword_automations",
    "api_access",
    COMMERCE_FEATURE,
    ANALYTICS_FEATURE,
]

DEFAULT_PLANS: tuple[dict, ...] = (
    {
        "slug": "starter",
        "name": "Starter",
        "limits": {"whatsapp_numbers": 1, "members": 2, "contacts": 5_000},
        "features": [COMMERCE_FEATURE],
        "sort_order": 10,
    },
    {
        "slug": "growth",
        "name": "Growth",
        "limits": {"whatsapp_numbers": 2, "members": 5, "contacts": 25_000},
        "features": _ALL_FEATURES,
        "sort_order": 20,
    },
    {
        "slug": "pro",
        "name": "Pro",
        "limits": {"whatsapp_numbers": 5, "members": 15, "contacts": 1_00_000},
        "features": _ALL_FEATURES,
        "sort_order": 30,
    },
)


def plan_fields(spec: dict) -> dict:
    """Model field values for a ``DEFAULT_PLANS`` entry (no prices: those come from Razorpay)."""
    return {
        "name": spec["name"],
        "limits": dict(spec["limits"]),
        "features": list(spec["features"]),
        "is_active": True,
        "sort_order": spec["sort_order"],
    }


def ensure_default_plans() -> None:
    from .models import Plan

    for spec in DEFAULT_PLANS:
        Plan.objects.get_or_create(slug=spec["slug"], defaults=plan_fields(spec))
