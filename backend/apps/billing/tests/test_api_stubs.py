"""Billing API contract stubs, the Razorpay webhook stub and the entitlements contract."""

import pytest

from apps.billing import entitlements
from common.exceptions import Conflict
from common.roles import Role
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

BASE = "/api/v1/billing"

PROFILE = {
    "legal_name": "Asha Traders Private Limited",
    "gstin": "29abcde1234f1z5",
    "email": "accounts@asha.example",
    "address_line1": "12 MG Road",
    "city": "Bengaluru",
    "state_code": "29",
    "postal_code": "560001",
}


def assert_not_implemented(response):
    assert response.status_code == 501, response.content
    assert response.json()["error"]["code"] == "not_implemented"


def assert_insufficient_role(response):
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "insufficient_role"


@pytest.mark.parametrize("url", [f"{BASE}/plans/", f"{BASE}/subscription/", f"{BASE}/usage/"])
def test_viewer_reads_are_stubbed(auth_client, url):
    assert_not_implemented(auth_client(Role.VIEWER).get(url))


@pytest.mark.parametrize("url", [f"{BASE}/billing-profile/", f"{BASE}/invoices/"])
def test_billing_details_need_admin(auth_client, url):
    assert_insufficient_role(auth_client(Role.AGENT).get(url))
    assert_not_implemented(auth_client(Role.ADMIN).get(url))


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", f"{BASE}/subscription/checkout/", {"plan_id": "growth", "interval": "monthly"}),
        (
            "post",
            f"{BASE}/subscription/verify/",
            {
                "razorpay_payment_id": "pay_1",
                "razorpay_subscription_id": "sub_1",
                "razorpay_signature": "sig",
            },
        ),
        ("post", f"{BASE}/subscription/cancel/", {}),
        ("patch", f"{BASE}/billing-profile/", PROFILE),
    ],
)
def test_changes_need_owner(auth_client, method, url, body):
    assert_insufficient_role(getattr(auth_client(Role.ADMIN), method)(url, body, format="json"))
    assert_not_implemented(getattr(auth_client(Role.OWNER), method)(url, body, format="json"))


def test_non_members_get_404(user, other_workspace):
    response = make_api_client(user, other_workspace).get(f"{BASE}/subscription/")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"plan_id": "enterprise", "interval": "monthly"}, "plan_id"),
        ({"plan_id": "pro", "interval": "weekly"}, "interval"),
        ({"interval": "annual"}, "plan_id"),
    ],
)
def test_checkout_validation(auth_client, body, field):
    response = auth_client().post(f"{BASE}/subscription/checkout/", body, format="json")

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"gstin": "29ABCDE1234F1Z"}, "gstin"),
        ({"state_code": "27"}, "state_code"),
        ({"postal_code": "5600"}, "postal_code"),
        ({"email": "not-an-email"}, "email"),
    ],
)
def test_billing_profile_validation(auth_client, changes, field):
    response = auth_client().patch(
        f"{BASE}/billing-profile/", {**PROFILE, **changes}, format="json"
    )

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]


def test_unregistered_business_may_leave_gstin_blank(auth_client):
    body = {**PROFILE, "gstin": "", "state_code": "27"}

    assert_not_implemented(auth_client().patch(f"{BASE}/billing-profile/", body, format="json"))


def test_billing_profile_serializer_normalises_gstin():
    from apps.billing.serializers import BillingProfileSerializer

    serializer = BillingProfileSerializer(data={**PROFILE, "gstin": " 29abcde1234f1z5 "})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["gstin"] == "29ABCDE1234F1Z5"


def test_razorpay_webhook_is_stubbed(client):
    response = client.post("/webhooks/razorpay/", data=b"{}", content_type="application/json")

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


def test_razorpay_webhook_rejects_get(client):
    assert client.get("/webhooks/razorpay/").status_code == 405


# --- Entitlements contract (allow-all until billing lands) ----------------------------------


def test_entitlement_keys():
    assert entitlements.METRICS == ("whatsapp_numbers", "members", "contacts")
    assert set(entitlements.FEATURES) == {
        entitlements.SCHEDULED_CAMPAIGNS,
        entitlements.KEYWORD_AUTOMATIONS,
        entitlements.API_ACCESS,
    }


def test_stubs_allow_everything(workspace):
    for feature in entitlements.FEATURES:
        assert entitlements.has_feature(workspace, feature) is True
    for metric in entitlements.METRICS:
        assert entitlements.remaining_quota(workspace, metric) is None
        entitlements.check_quota(workspace, metric, amount=10_000)
        assert entitlements.record_usage(workspace, metric, 1, key="event-1") is None


def test_unknown_keys_are_programming_errors(workspace):
    with pytest.raises(ValueError):
        entitlements.has_feature(workspace, "teleport")
    with pytest.raises(ValueError):
        entitlements.remaining_quota(workspace, "planets")
    with pytest.raises(ValueError):
        entitlements.check_quota(workspace, "planets")
    with pytest.raises(ValueError):
        entitlements.record_usage(workspace, entitlements.CONTACTS, 1, key="")


def test_check_quota_raises_when_remaining_is_too_low(workspace, monkeypatch):
    monkeypatch.setattr(entitlements, "remaining_quota", lambda workspace, metric: 2)

    entitlements.check_quota(workspace, entitlements.CONTACTS, amount=2)
    with pytest.raises(entitlements.QuotaExceeded) as excinfo:
        entitlements.check_quota(workspace, entitlements.CONTACTS, amount=3)

    assert isinstance(excinfo.value, Conflict)
    assert excinfo.value.status_code == 409
    assert excinfo.value.get_codes() == "quota_exceeded"
