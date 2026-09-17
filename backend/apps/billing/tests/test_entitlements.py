"""Entitlements: plan limits and features per subscription status."""

import json

import pytest
from rest_framework.renderers import JSONRenderer

from apps.billing import entitlements, services
from apps.billing.entitlements import (
    API_ACCESS,
    COMMERCE,
    CONTACTS,
    FEATURES,
    MEMBERS,
    METRICS,
    WHATSAPP_NUMBERS,
    QuotaExceeded,
)
from apps.billing.models import Plan, Subscription, UsageRecord
from apps.contacts.factories import ContactFactory
from apps.tenants.factories import MembershipFactory
from apps.whatsapp.factories import PhoneNumberFactory
from common.exceptions import Conflict, api_exception_handler

pytestmark = pytest.mark.django_db


def set_status(workspace, status: str, plan: str = "growth") -> None:
    subscription = services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(status=status, plan_id=plan)
    entitlements.clear_cache(workspace)


def test_entitlement_keys():
    assert entitlements.METRICS == ("whatsapp_numbers", "members", "contacts")
    assert set(entitlements.FEATURES) == {
        entitlements.SCHEDULED_CAMPAIGNS,
        entitlements.KEYWORD_AUTOMATIONS,
        entitlements.API_ACCESS,
        entitlements.COMMERCE,
        entitlements.ANALYTICS,
    }
    assert entitlements.COMMERCE == "commerce"
    assert entitlements.ANALYTICS == "analytics"


def test_unknown_keys_are_programming_errors(workspace):
    with pytest.raises(ValueError):
        entitlements.has_feature(workspace, "teleport")
    with pytest.raises(ValueError):
        entitlements.remaining_quota(workspace, "planets")
    with pytest.raises(ValueError):
        entitlements.check_quota(workspace, "planets")
    with pytest.raises(ValueError):
        entitlements.record_usage(workspace, CONTACTS, 1, key="")


def test_a_growth_trial_includes_every_feature(workspace):
    assert all(entitlements.has_feature(workspace, feature) for feature in FEATURES)
    assert entitlements.remaining_quota(workspace, WHATSAPP_NUMBERS) == 2


@pytest.mark.parametrize("status", ["trialing", "active", "pending"])
def test_entitled_statuses_get_the_plan(workspace, status):
    set_status(workspace, status, plan="starter")
    ContactFactory.create_batch(2, workspace=workspace)

    # Starter only includes the store.
    assert [f for f in FEATURES if entitlements.has_feature(workspace, f)] == [COMMERCE]
    assert entitlements.remaining_quota(workspace, WHATSAPP_NUMBERS) == 1
    assert entitlements.remaining_quota(workspace, MEMBERS) == 1  # the owner uses one of two
    assert entitlements.remaining_quota(workspace, CONTACTS) == 4998
    entitlements.check_quota(workspace, CONTACTS, amount=4998)
    with pytest.raises(QuotaExceeded):
        entitlements.check_quota(workspace, CONTACTS, amount=4999)


@pytest.mark.parametrize("status", ["halted", "cancelled", "expired"])
def test_restricted_statuses_freeze_usage(workspace, status):
    set_status(workspace, status, plan="pro")
    PhoneNumberFactory(waba__workspace=workspace)

    assert not any(entitlements.has_feature(workspace, feature) for feature in FEATURES)
    for metric in METRICS:
        assert entitlements.remaining_quota(workspace, metric) == 0
    entitlements.check_quota(workspace, CONTACTS, amount=0)
    with pytest.raises(QuotaExceeded) as excinfo:
        entitlements.check_quota(workspace, WHATSAPP_NUMBERS)

    exc = excinfo.value
    assert (exc.metric, exc.limit, exc.used) == ("whatsapp_numbers", 1, 1)
    assert status in str(exc)


def test_unlimited_limits(workspace):
    Plan.objects.filter(slug="growth").update(
        limits={"whatsapp_numbers": 2, "members": 5, "contacts": None}
    )

    assert entitlements.remaining_quota(workspace, CONTACTS) is None
    entitlements.check_quota(workspace, CONTACTS, amount=10**9)


def test_quota_exceeded_error_envelope_has_details(workspace):
    MembershipFactory.create_batch(4, workspace=workspace)  # 5 members: Growth's limit

    with pytest.raises(QuotaExceeded) as excinfo:
        entitlements.check_quota(workspace, MEMBERS)

    exc = excinfo.value
    assert isinstance(exc, Conflict)
    assert exc.status_code == 409
    assert exc.get_codes() == "quota_exceeded"
    response = api_exception_handler(exc, {})
    assert response.status_code == 409
    assert json.loads(JSONRenderer().render(response.data)) == {
        "error": {
            "code": "quota_exceeded",
            "message": (
                "Your plan allows 5 team members and this workspace has 5. "
                "Upgrade your plan to add more."
            ),
            "details": {"metric": "members", "limit": 5, "used": 5},
        }
    }


def test_plain_quota_exceeded_keeps_the_default_envelope():
    response = api_exception_handler(QuotaExceeded(), {})

    assert response.data["error"]["code"] == "quota_exceeded"
    assert response.data["error"]["details"] is None
    assert QuotaExceeded().get_codes() == "quota_exceeded"


def test_the_plan_lookup_is_memoised_per_workspace_instance(workspace, django_assert_num_queries):
    assert entitlements.has_feature(workspace, API_ACCESS)

    with django_assert_num_queries(0):
        assert entitlements.has_feature(workspace, API_ACCESS)
        assert entitlements.get_entitlements(workspace).plan_slug == "growth"

    set_status(workspace, "expired")
    assert not entitlements.has_feature(workspace, API_ACCESS)


def test_record_usage_is_idempotent_on_key(workspace, other_workspace):
    entitlements.record_usage(workspace, CONTACTS, 5, key="contacts:import:1")
    entitlements.record_usage(workspace, CONTACTS, 7, key="contacts:import:1")
    entitlements.record_usage(other_workspace, CONTACTS, 1, key="contacts:import:1")

    assert list(
        UsageRecord.objects.filter(workspace=workspace).values_list("amount", flat=True)
    ) == [5]
    assert UsageRecord.objects.filter(workspace=other_workspace).count() == 1
    with pytest.raises(ValueError):
        entitlements.record_usage(workspace, CONTACTS, 1, key="k" * 256)
