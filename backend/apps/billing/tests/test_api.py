"""Billing API: roles, tenant isolation, plans, subscription, checkout, profile, invoices, usage."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing import services
from apps.billing.models import BillingProfile, Plan, Subscription
from apps.billing.razorpay import RazorpayError
from apps.billing.tests.helpers import (
    KARNATAKA_PROFILE,
    MAHARASHTRA_PROFILE,
    checkout_signature,
    make_active,
)
from apps.contacts.factories import ContactFactory
from apps.whatsapp.factories import PhoneNumberFactory
from apps.whatsapp.models import PhoneNumber
from common.roles import Role
from common.testing import assert_tenant_isolated, make_api_client

pytestmark = pytest.mark.django_db

BASE = "/api/v1/billing"
PLANS = f"{BASE}/plans/"
SUBSCRIPTION = f"{BASE}/subscription/"
CHECKOUT = f"{BASE}/subscription/checkout/"
VERIFY = f"{BASE}/subscription/verify/"
CANCEL = f"{BASE}/subscription/cancel/"
PROFILE = f"{BASE}/billing-profile/"
INVOICES = f"{BASE}/invoices/"
USAGE = f"{BASE}/usage/"


def error(response, status: int) -> dict:
    assert response.status_code == status, response.content
    return response.json()["error"]


@pytest.fixture
def profile(workspace):
    return BillingProfile.objects.create(workspace=workspace, **MAHARASHTRA_PROFILE)


def start_checkout(auth_client, plan_id="pro", interval="monthly") -> str:
    response = auth_client().post(
        CHECKOUT, {"plan_id": plan_id, "interval": interval}, format="json"
    )
    assert response.status_code == 200, response.content
    return response.json()["subscription_id"]


def verify_body(subscription_id: str, payment_id: str = "pay_1") -> dict:
    return {
        "razorpay_payment_id": payment_id,
        "razorpay_subscription_id": subscription_id,
        "razorpay_signature": checkout_signature(payment_id, subscription_id),
    }


# --- Roles and isolation --------------------------------------------------------------------


@pytest.mark.parametrize("url", [PLANS, SUBSCRIPTION, USAGE])
def test_any_member_can_read(auth_client, url):
    assert auth_client(Role.VIEWER).get(url).status_code == 200


@pytest.mark.parametrize("url", [PROFILE, INVOICES])
def test_billing_details_need_admin(auth_client, url):
    assert error(auth_client(Role.AGENT).get(url), 403)["code"] == "insufficient_role"
    assert auth_client(Role.ADMIN).get(url).status_code == 200


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", CHECKOUT, {"plan_id": "growth", "interval": "monthly"}),
        ("post", VERIFY, verify_body("sub_1")),
        ("post", CANCEL, {}),
        ("patch", PROFILE, MAHARASHTRA_PROFILE),
    ],
)
def test_changes_need_owner(auth_client, method, url, body):
    response = getattr(auth_client(Role.ADMIN), method)(url, body, format="json")

    assert error(response, 403)["code"] == "insufficient_role"


@pytest.mark.parametrize("url", [PLANS, SUBSCRIPTION, USAGE, PROFILE, INVOICES])
def test_non_members_get_404(user, other_workspace, url):
    assert make_api_client(user, other_workspace).get(url).status_code == 404


# --- Plans and subscription -----------------------------------------------------------------


def test_plans_list_prices_limits_and_features(auth_client):
    response = auth_client(Role.VIEWER).get(PLANS)

    assert response.status_code == 200
    plans = {plan["id"]: plan for plan in response.json()}
    assert list(plans) == ["starter", "growth", "pro"]
    assert plans["growth"] == {
        "id": "growth",
        "name": "Growth",
        "monthly_price_paise": 249900,
        "annual_price_paise": 2499000,
        "limits": {"whatsapp_numbers": 2, "members": 5, "contacts": 25000},
        "features": ["scheduled_campaigns", "keyword_automations", "api_access"],
    }
    assert plans["starter"]["features"] == []


def test_inactive_plans_are_hidden(auth_client):
    Plan.objects.filter(slug="pro").update(is_active=False)

    assert [plan["id"] for plan in auth_client().get(PLANS).json()] == ["starter", "growth"]


def test_first_read_starts_a_14_day_growth_trial(auth_client, workspace):
    before = timezone.now()

    body = auth_client(Role.VIEWER).get(SUBSCRIPTION).json()
    auth_client().get(SUBSCRIPTION)

    assert body["status"] == "trialing"
    assert body["plan"]["id"] == "growth"
    assert body["interval"] == "monthly"
    assert body["cancel_at_period_end"] is False
    assert body["current_period_start"] is None
    subscription = Subscription.objects.get(workspace=workspace)
    trial = timedelta(days=14)
    assert before + trial <= subscription.trial_ends_at <= timezone.now() + trial


# --- Billing profile ------------------------------------------------------------------------


def test_billing_profile_starts_empty(auth_client, workspace):
    response = auth_client(Role.ADMIN).get(PROFILE)

    assert response.status_code == 200
    assert response.json() == dict.fromkeys(MAHARASHTRA_PROFILE, "")
    assert BillingProfile.objects.filter(workspace=workspace).count() == 1


def test_owner_updates_billing_profile(auth_client, workspace):
    body = {**MAHARASHTRA_PROFILE, "gstin": " 27aapfu0939f1zv "}

    response = auth_client().patch(PROFILE, body, format="json")

    assert response.status_code == 200, response.content
    assert response.json() == MAHARASHTRA_PROFILE
    profile = BillingProfile.objects.get(workspace=workspace)
    profile.full_clean()
    assert profile.is_complete


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"gstin": "27AAPFU0939F1Z"}, "gstin"),
        ({"gstin": "27AAPFU0939F1ZW"}, "gstin"),
        ({"state_code": "29"}, "state_code"),
        ({"gstin": "", "state_code": "40"}, "state_code"),
        ({"postal_code": "4000"}, "postal_code"),
        ({"email": "not-an-email"}, "email"),
    ],
)
def test_billing_profile_validation(auth_client, changes, field):
    response = auth_client().patch(PROFILE, {**MAHARASHTRA_PROFILE, **changes}, format="json")

    assert field in error(response, 400)["details"]


def test_partial_update_checks_gstin_against_the_stored_state(auth_client, profile):
    gstin_only = auth_client().patch(PROFILE, {"gstin": KARNATAKA_PROFILE["gstin"]}, format="json")
    both = auth_client().patch(
        PROFILE, {"gstin": KARNATAKA_PROFILE["gstin"], "state_code": "29"}, format="json"
    )

    assert "gstin" in error(gstin_only, 400)["details"]
    assert both.status_code == 200, both.content


def test_unregistered_business_may_leave_gstin_blank(auth_client):
    response = auth_client().patch(PROFILE, {**MAHARASHTRA_PROFILE, "gstin": ""}, format="json")

    assert response.status_code == 200, response.content


# --- Checkout and verification --------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"plan_id": "enterprise", "interval": "monthly"}, "plan_id"),
        ({"plan_id": "pro", "interval": "weekly"}, "interval"),
        ({"interval": "annual"}, "plan_id"),
    ],
)
def test_checkout_validation(auth_client, body, field):
    assert field in error(auth_client().post(CHECKOUT, body, format="json"), 400)["details"]


def test_checkout_requires_a_complete_billing_profile(auth_client, workspace, fake_razorpay):
    body = {"plan_id": "pro", "interval": "annual"}

    first = auth_client().post(CHECKOUT, body, format="json")
    BillingProfile.objects.filter(workspace=workspace).update(legal_name="Asha Traders")
    second = auth_client().post(CHECKOUT, body, format="json")

    assert error(first, 409)["code"] == "billing_profile_required"
    assert error(second, 409)["code"] == "billing_profile_required"
    assert fake_razorpay.calls == []


def test_checkout_creates_a_razorpay_subscription(auth_client, workspace, profile, fake_razorpay):
    response = auth_client().post(CHECKOUT, {"plan_id": "pro", "interval": "annual"}, format="json")

    assert response.status_code == 200, response.content
    assert response.json() == {
        "key_id": "rzp_test_key",
        "subscription_id": "sub_fake000001",
        "name": "UpChatz",
        "description": "Pro plan: ₹59,990 + 18% GST per year",
        "prefill": {"name": profile.legal_name, "email": profile.email},
    }
    [call] = fake_razorpay.calls_to("create_subscription")
    assert call == {
        "plan_id": "plan_test_pro_annual",
        "total_count": 10,
        "notes": {"workspace_id": str(workspace.pk), "plan": "pro", "interval": "annual"},
    }
    subscription = Subscription.objects.get(workspace=workspace)
    assert subscription.status == "pending"
    assert subscription.razorpay_subscription_id == "sub_fake000001"
    assert subscription.plan_id == "growth"  # the trial plan stays until activation
    assert (subscription.checkout_plan_id, subscription.checkout_interval) == ("pro", "annual")
    assert subscription.trial_ends_at is not None


def test_repeated_checkout_reuses_the_open_razorpay_subscription(
    auth_client, profile, fake_razorpay
):
    first = start_checkout(auth_client, "growth", "monthly")
    second = start_checkout(auth_client, "growth", "monthly")

    assert first == second
    assert len(fake_razorpay.calls_to("create_subscription")) == 1


def test_checkout_for_another_plan_replaces_the_open_one(
    auth_client, workspace, profile, fake_razorpay
):
    first = start_checkout(auth_client, "growth", "monthly")
    second = start_checkout(auth_client, "starter", "monthly")

    assert second != first
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": first, "at_cycle_end": False}
    ]
    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.razorpay_subscription_id, subscription.checkout_plan_id) == (
        second,
        "starter",
    )


def test_checkout_is_refused_while_active(auth_client, workspace, profile, fake_razorpay):
    make_active(workspace)

    response = auth_client().post(CHECKOUT, {"plan_id": "pro", "interval": "monthly"})

    assert error(response, 409)["code"] == "subscription_active"
    assert fake_razorpay.calls == []


def test_checkout_reports_razorpay_outages(auth_client, workspace, profile, fake_razorpay):
    fake_razorpay.fail_with = RazorpayError("Razorpay is down")

    response = auth_client().post(CHECKOUT, {"plan_id": "pro", "interval": "monthly"})

    assert error(response, 503)["code"] == "upstream_unavailable"
    subscription = services.get_subscription(workspace)
    assert (subscription.status, subscription.razorpay_subscription_id) == ("trialing", None)


def test_checkout_without_razorpay_plan_ids_is_unavailable(auth_client, profile, settings):
    settings.RAZORPAY_PLAN_IDS = {}

    response = auth_client().post(CHECKOUT, {"plan_id": "pro", "interval": "monthly"})

    assert error(response, 503)["code"] == "upstream_unavailable"


def test_verify_accepts_a_valid_signature(auth_client, profile):
    subscription_id = start_checkout(auth_client)

    response = auth_client().post(VERIFY, verify_body(subscription_id), format="json")

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "pending"  # the webhook will activate it


def test_verify_syncs_an_authorised_subscription(auth_client, workspace, profile, fake_razorpay):
    subscription_id = start_checkout(auth_client, "pro", "monthly")
    now = timezone.now()
    fake_razorpay.subscriptions[subscription_id].update(
        status="active",
        current_start=int(now.timestamp()),
        current_end=int((now + timedelta(days=30)).timestamp()),
        customer_id="cust_9",
    )

    response = auth_client().post(VERIFY, verify_body(subscription_id), format="json")

    body = response.json()
    assert (body["status"], body["plan"]["id"], body["interval"]) == ("active", "pro", "monthly")
    assert body["current_period_end"] is not None
    subscription = Subscription.objects.get(workspace=workspace)
    assert subscription.activated_at is not None
    assert subscription.checkout_plan_id is None
    assert subscription.razorpay_customer_id == "cust_9"


@pytest.mark.parametrize("tamper", ["signature", "subscription"])
def test_verify_rejects_bad_signatures(auth_client, workspace, profile, tamper):
    subscription_id = start_checkout(auth_client)
    body = verify_body(subscription_id)
    if tamper == "signature":
        body["razorpay_signature"] = "0" * 64
    else:  # correctly signed, but not this workspace's subscription
        body = verify_body("sub_someone_else")

    response = auth_client().post(VERIFY, body, format="json")

    assert error(response, 400)["code"] == "payment_verification_failed"
    assert services.get_subscription(workspace).status == "pending"


def test_verify_without_a_checkout_fails(auth_client):
    response = auth_client().post(VERIFY, verify_body("sub_1"), format="json")

    assert error(response, 400)["code"] == "payment_verification_failed"


# --- Cancellation ---------------------------------------------------------------------------


def test_trial_cancelled_at_period_end_keeps_the_trial(auth_client):
    body = auth_client().post(CANCEL, {}, format="json").json()

    assert (body["status"], body["cancel_at_period_end"]) == ("trialing", True)


def test_trial_cancelled_immediately(auth_client):
    body = auth_client().post(CANCEL, {"at_period_end": False}, format="json").json()

    assert body["status"] == "cancelled"


def test_active_cancelled_at_period_end(auth_client, workspace, fake_razorpay):
    make_active(workspace)
    fake_razorpay.subscriptions["sub_active1"] = {"id": "sub_active1", "status": "active"}

    body = auth_client().post(CANCEL, {"at_period_end": True}, format="json").json()

    assert (body["status"], body["cancel_at_period_end"]) == ("active", True)
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": "sub_active1", "at_cycle_end": True}
    ]


def test_active_cancelled_immediately(auth_client, workspace, fake_razorpay):
    make_active(workspace)
    fake_razorpay.subscriptions["sub_active1"] = {"id": "sub_active1", "status": "active"}

    first = auth_client().post(CANCEL, {"at_period_end": False}, format="json").json()
    second = auth_client().post(CANCEL, {"at_period_end": False}, format="json").json()

    assert (first["status"], first["cancel_at_period_end"]) == ("cancelled", False)
    assert second["status"] == "cancelled"
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": "sub_active1", "at_cycle_end": False}
    ]


def test_cancelling_an_open_checkout_returns_to_the_trial(
    auth_client, workspace, profile, fake_razorpay
):
    subscription_id = start_checkout(auth_client)

    body = auth_client().post(CANCEL, {}, format="json").json()

    assert (body["status"], body["cancel_at_period_end"]) == ("trialing", True)
    assert services.get_subscription(workspace).razorpay_subscription_id is None
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": subscription_id, "at_cycle_end": False}
    ]


def test_cancel_reports_razorpay_outages(auth_client, workspace, fake_razorpay):
    make_active(workspace)
    fake_razorpay.fail_with = RazorpayError("Razorpay is down")

    response = auth_client().post(CANCEL, {"at_period_end": False}, format="json")

    assert error(response, 503)["code"] == "upstream_unavailable"
    assert services.get_subscription(workspace).status == "active"


# --- Invoices -------------------------------------------------------------------------------


def make_invoice(workspace, payment_id: str, issued_at):
    subscription = services.get_subscription(workspace)
    invoice, _ = services.create_paid_invoice(
        subscription=subscription,
        payment_id=payment_id,
        issued_at=issued_at,
        period_start=issued_at,
        period_end=issued_at + timedelta(days=30),
    )
    return invoice


def test_invoices_are_listed_newest_first(auth_client, workspace, profile):
    now = timezone.now()
    older = make_invoice(workspace, "pay_a", now - timedelta(days=40))
    newer = make_invoice(workspace, "pay_b", now)

    response = auth_client(Role.ADMIN).get(INVOICES)

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["id"] for item in results] == [str(newer.pk), str(older.pk)]
    item = results[0]
    assert item["number"] == newer.number
    assert item["status"] == "paid"
    assert (item["subtotal_paise"], item["cgst_paise"], item["sgst_paise"]) == (249900, 0, 0)
    assert (item["igst_paise"], item["total_paise"]) == (44982, 294882)
    assert item["download_url"] is None


def test_invoices_are_paginated(auth_client, workspace, profile):
    for index in range(3):
        make_invoice(workspace, f"pay_{index}", timezone.now())

    body = auth_client(Role.ADMIN).get(f"{INVOICES}?page_size=2").json()

    assert len(body["results"]) == 2
    assert body["next"] is not None


def test_invoices_are_tenant_isolated(auth_client, other_workspace):
    invoice = make_invoice(other_workspace, "pay_other", timezone.now())

    assert_tenant_isolated(auth_client(Role.ADMIN), object_id=invoice.pk, list_url=INVOICES)


# --- Usage ----------------------------------------------------------------------------------


def test_usage_counts_numbers_members_and_contacts(auth_client, workspace):
    auth_client(Role.AGENT)
    PhoneNumberFactory(waba__workspace=workspace)
    PhoneNumberFactory(
        waba__workspace=workspace,
        registration_status=PhoneNumber.RegistrationStatus.DEREGISTERED,
    )
    PhoneNumberFactory()  # another workspace
    ContactFactory.create_batch(3, workspace=workspace)
    ContactFactory()  # another workspace

    response = auth_client(Role.VIEWER).get(USAGE)

    assert response.json() == {
        "metrics": [
            {"key": "whatsapp_numbers", "used": 1, "limit": 2},
            {"key": "members", "used": 3, "limit": 5},
            {"key": "contacts", "used": 3, "limit": 25000},
        ]
    }


def test_usage_limits_equal_usage_when_restricted(auth_client, workspace):
    subscription = services.get_subscription(workspace)
    subscription.status = "expired"
    subscription.save()

    response = auth_client(Role.VIEWER).get(USAGE)

    assert response.json() == {
        "metrics": [
            {"key": "whatsapp_numbers", "used": 0, "limit": 0},
            {"key": "members", "used": 2, "limit": 2},
            {"key": "contacts", "used": 0, "limit": 0},
        ]
    }
