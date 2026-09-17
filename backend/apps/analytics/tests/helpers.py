"""Shared helpers for the analytics tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from apps.billing import entitlements, services
from apps.billing.models import Plan, Subscription
from apps.billing.plans import ensure_default_plans
from apps.inbox.factories import MessageFactory

IST = ZoneInfo("Asia/Kolkata")
# Tests run on "today" = 2026-03-15 in IST.
NOW = datetime(2026, 3, 15, 12, 0, tzinfo=IST)

BASE = "/api/v1/analytics/"
REPORTS = ("overview", "messages", "templates", "campaigns", "team", "commerce")


def url(name: str, **params) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{BASE}{name}/" + (f"?{query}" if query else "")


def local(value: str, zone=IST) -> datetime:
    """``"2026-03-10 23:30"`` as an aware datetime in ``zone``."""
    return datetime.fromisoformat(value).replace(tzinfo=zone)


def backdate(instance, value: datetime, field: str = "created_at"):
    type(instance).objects.filter(pk=instance.pk).update(**{field: value})
    setattr(instance, field, value)
    return instance


def message(conversation, when: str, **fields):
    """A message in ``conversation`` created at local IST time ``when``."""
    return backdate(MessageFactory(conversation=conversation, **fields), local(when))


def set_plan(workspace, slug: str) -> None:
    subscription = services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(plan_id=slug)
    entitlements.clear_cache(workspace)


def drop_feature(slug: str, feature: str) -> None:
    ensure_default_plans()  # a transactional test elsewhere may have flushed the seeded rows
    plan = Plan.objects.get(slug=slug)
    plan.features = [f for f in plan.features if f != feature]
    plan.save(update_fields=["features"])
