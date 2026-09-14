import pytest

from apps.automations import demo
from apps.automations.models import AutomationRule, BusinessHours

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent(workspace):
    demo.seed(workspace)
    demo.seed(workspace)

    rules = AutomationRule.objects.filter(workspace=workspace)
    assert sorted(rules.values_list("trigger", flat=True)) == [
        "first_inbound",
        "keyword",
        "outside_business_hours",
    ]
    assert rules.get(trigger="keyword").keywords == ["price", "prices", "rate"]
    hours = BusinessHours.objects.get(workspace=workspace)
    assert hours.enabled
    assert hours.schedule == [{"day": day, "start": "10:00", "end": "19:00"} for day in range(6)]


def test_seed_keeps_existing_hours_and_rules(workspace):
    custom = [{"day": 0, "start": "08:00", "end": "12:00"}]
    BusinessHours.objects.create(workspace=workspace, enabled=False, schedule=custom)
    AutomationRule.objects.create(
        workspace=workspace, name="Welcome message", trigger="new_contact", actions=[]
    )

    demo.seed(workspace)

    hours = BusinessHours.objects.get(workspace=workspace)
    assert (hours.enabled, hours.schedule) == (False, custom)
    assert AutomationRule.objects.get(workspace=workspace, name="Welcome message").trigger == (
        "new_contact"
    )
    assert AutomationRule.objects.filter(workspace=workspace).count() == 3
