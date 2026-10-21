"""Razorpay plan billing in both modes: one-time (prepaid) orders next to auto-pay subscriptions.

Checkout and verify of Razorpay orders, the signed ``order.paid`` webhook, renewals, switching
between modes, expiry, reminders and cancellation of Razorpay prepaid plans, ``payment_mode`` on
the API and the data migration that marks Cashfree plans prepaid."""

import importlib
import re
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.core import mail
from django.utils import timezone

from apps.billing import services
from apps.billing.models import (
    BillingOrder,
    BillingProfile,
    Invoice,
    PaymentMode,
    Plan,
    RazorpayEvent,
    RazorpayPlan,
    Subscription,
)
from apps.billing.razorpay import RazorpayError
from apps.billing.schema_enums import PAYMENT_MODES
from apps.billing.tests.helpers import (
    MAHARASHTRA_PROFILE,
    make_active,
    make_cashfree_active,
    make_razorpay_prepaid_active,
    order_paid_event,
    order_signature,
    post_webhook,
    subscription_event,
    ts,
)
from apps.tenants.factories import WorkspaceFactory
from common.roles import Role

pytestmark = pytest.mark.django_db

BASE = "/api/v1/billing"
SUBSCRIPTION = f"{BASE}/subscription/"
CHECKOUT = f"{BASE}/subscription/checkout/"
VERIFY = f"{BASE}/subscription/verify/"
CANCEL = f"{BASE}/subscription/cancel/"

GROWTH_MONTHLY_TOTAL = 294882  # 249900 + 18% GST (IGST for a Maharashtra buyer)
PREPAID_MESSAGE = "You can switch to auto-pay when your paid period ends."


@pytest.fixture(autouse=True)
def _razorpay_billing(settings):
    settings.BILLING_PROVIDER = "razorpay"


@pytest.fixture
def profile(workspace):
    """A complete billing profile without a phone: Razorpay doesn't need one."""
    return BillingProfile.objects.create(workspace=workspace, **MAHARASHTRA_PROFILE)


def error(response, status: int) -> dict:
    assert response.status_code == status, response.content
    return response.json()["error"]


def pay_once(auth_client, plan_id="growth", interval="monthly") -> dict:
    response = auth_client().post(
        CHECKOUT,
        {"plan_id": plan_id, "interval": interval, "payment_mode": "one_time"},
        format="json",
    )
    assert response.status_code == 200, response.content
    return response.json()


def verify_body(order_id: str, payment_id: str = "pay_once0001") -> dict:
    return {
        "razorpay_payment_id": payment_id,
        "razorpay_order_id": order_id,
        "razorpay_signature": order_signature(payment_id, order_id),
    }


def paid_order(auth_client, fake_razorpay, payment_id="pay_once0001", **checkout) -> str:
    order_id = pay_once(auth_client, **checkout)["order_id"]
    fake_razorpay.pay_order(order_id, payment_id=payment_id)
    return order_id


def approx(moment, expected, seconds: int = 60) -> bool:
    return abs((moment - expected).total_seconds()) < seconds


def make_autopay_active(workspace) -> Subscription:
    subscription = make_active(workspace)
    subscription.provider = "razorpay"
    subscription.save()
    return subscription


# --- Checkout -------------------------------------------------------------------------------


def test_one_time_checkout_creates_a_razorpay_order(auth_client, workspace, profile, fake_razorpay):
    session = pay_once(auth_client)

    assert session == {
        "provider": "razorpay",
        "payment_mode": "one_time",
        "name": "UpChatz",
        "description": "Growth plan: ₹2,499 + 18% GST per month",
        "prefill": {"name": profile.legal_name, "email": profile.email},
        "key_id": "rzp_test_key",
        "subscription_id": None,
        "order_id": "order_fake000001",
        "payment_session_id": None,
        "mode": None,
        "amount_paise": GROWTH_MONTHLY_TOTAL,
    }
    [call] = fake_razorpay.calls_to("create_order")
    assert (call["amount"], call["currency"]) == (GROWTH_MONTHLY_TOTAL, "INR")
    assert re.fullmatch(r"upc_[0-9a-f]{32}", call["receipt"])
    assert len(call["receipt"]) <= 40
    assert call["notes"] == {
        "workspace_id": str(workspace.pk),
        "plan": "growth",
        "interval": "monthly",
    }
    assert fake_razorpay.calls_to("create_subscription") == []
    order = BillingOrder.objects.get(order_id="order_fake000001")
    assert (order.workspace_id, order.provider, order.plan_id, order.interval) == (
        workspace.pk,
        "razorpay",
        "growth",
        "monthly",
    )
    assert (order.amount_paise, order.status, order.payment_session_id) == (
        GROWTH_MONTHLY_TOTAL,
        "created",
        "",
    )
    # Nothing changes until the order is paid.
    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.status, subscription.provider, subscription.prepaid) == (
        "trialing",
        "",
        False,
    )


def test_one_time_amount_follows_the_gst_setting(auth_client, profile, settings):
    settings.BILLING_GST_ENABLED = False
    RazorpayPlan.objects.all().delete()  # the fake prices plans for the current GST setting

    assert pay_once(auth_client)["amount_paise"] == 249900


@pytest.mark.parametrize("gst_enabled", [True, False])
def test_pay_once_charges_the_razorpay_plan_amount(
    auth_client, profile, settings, fake_razorpay, gst_enabled
):
    settings.BILLING_GST_ENABLED = gst_enabled
    RazorpayPlan.objects.all().delete()
    fake_razorpay.add_plan("plan_test_growth_monthly", amount=GROWTH_MONTHLY_TOTAL)

    session = pay_once(auth_client)

    # With GST on, 2,499.00 + 18% = 2,948.82 is a base that adds up exactly.
    assert session["amount_paise"] == GROWTH_MONTHLY_TOTAL
    assert fake_razorpay.calls_to("create_order")[0]["amount"] == GROWTH_MONTHLY_TOTAL


@pytest.mark.parametrize("payment_mode", ["one_time", "autopay"])
def test_checkout_of_an_unconfigured_interval_is_plan_unavailable(
    auth_client, profile, settings, fake_razorpay, payment_mode
):
    settings.RAZORPAY_PLAN_IDS = {"growth": {"monthly": "plan_test_growth_monthly"}}

    response = auth_client().post(
        CHECKOUT,
        {"plan_id": "growth", "interval": "annual", "payment_mode": payment_mode},
        format="json",
    )

    assert error(response, 409)["code"] == "plan_unavailable"
    assert fake_razorpay.calls == []
    assert not BillingOrder.objects.exists()


@pytest.mark.parametrize("payment_mode", ["one_time", "autopay"])
def test_checkout_of_a_missing_razorpay_plan_is_plan_unavailable(
    auth_client, profile, fake_razorpay, payment_mode
):
    Plan.objects.filter(slug="growth").update(razorpay_plan_id_monthly="plan_gone")

    response = auth_client().post(
        CHECKOUT,
        {"plan_id": "growth", "interval": "monthly", "payment_mode": payment_mode},
        format="json",
    )

    assert error(response, 409)["code"] == "plan_unavailable"
    assert [name for name, _ in fake_razorpay.calls] == ["fetch_plan"]


@pytest.mark.parametrize("payment_mode", ["one_time", "autopay"])
def test_checkout_while_razorpay_cant_price_the_plan_is_upstream_unavailable(
    auth_client, profile, fake_razorpay, payment_mode
):
    RazorpayPlan.objects.all().delete()
    fake_razorpay.fail_with = RazorpayError("Razorpay returned HTTP 502.", status_code=502)

    response = auth_client().post(
        CHECKOUT,
        {"plan_id": "growth", "interval": "monthly", "payment_mode": payment_mode},
        format="json",
    )

    assert error(response, 503)["code"] == "upstream_unavailable"
    assert not BillingOrder.objects.exists()


def test_autopay_checkout_uses_the_plan_field(auth_client, profile, fake_razorpay):
    fake_razorpay.add_plan("plan_NewGrowth01", amount=GROWTH_MONTHLY_TOTAL)
    Plan.objects.filter(slug="growth").update(razorpay_plan_id_monthly="plan_NewGrowth01")

    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly"}, format="json"
    )

    assert response.status_code == 200, response.content
    assert fake_razorpay.calls_to("create_subscription")[0]["plan_id"] == "plan_NewGrowth01"


def test_razorpay_defaults_to_autopay(auth_client, profile, fake_razorpay):
    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly"}, format="json"
    )

    session = response.json()
    assert (session["payment_mode"], session["subscription_id"]) == ("autopay", "sub_fake000001")
    assert session["order_id"] is None
    assert fake_razorpay.calls_to("create_order") == []


def test_cashfree_defaults_to_one_time(auth_client, workspace, settings, fake_cashfree):
    settings.BILLING_PROVIDER = "cashfree"
    BillingProfile.objects.create(workspace=workspace, phone="+919876543210", **MAHARASHTRA_PROFILE)

    default = auth_client().post(CHECKOUT, {"plan_id": "growth", "interval": "monthly"})
    explicit = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly", "payment_mode": "one_time"}
    )

    for response in (default, explicit):
        assert response.status_code == 200, response.content
        assert (response.json()["provider"], response.json()["payment_mode"]) == (
            "cashfree",
            "one_time",
        )


def test_autopay_on_cashfree_is_invalid(auth_client, profile, settings, fake_cashfree):
    settings.BILLING_PROVIDER = "cashfree"

    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly", "payment_mode": "autopay"}
    )

    body = error(response, 400)
    assert body["code"] == "invalid"
    assert "payment_mode" in body["details"]
    assert fake_cashfree.calls == []


def test_unknown_payment_mode_is_invalid(auth_client, profile):
    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly", "payment_mode": "monthly"}
    )

    assert "payment_mode" in error(response, 400)["details"]


def test_one_time_checkout_needs_a_complete_profile(auth_client, workspace, fake_razorpay):
    BillingProfile.objects.create(workspace=workspace, legal_name="Asha Traders")

    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly", "payment_mode": "one_time"}
    )

    assert error(response, 409)["code"] == "billing_profile_required"
    assert fake_razorpay.calls == []


def test_one_time_checkout_reports_razorpay_outages(auth_client, profile, fake_razorpay):
    fake_razorpay.fail_with = RazorpayError("Gateway down", status_code=503)

    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly", "payment_mode": "one_time"}
    )

    assert error(response, 503)["code"] == "upstream_unavailable"
    assert not BillingOrder.objects.exists()


# --- Switching between modes ----------------------------------------------------------------


def test_one_time_is_refused_while_autopay_is_active(
    auth_client, workspace, profile, fake_razorpay
):
    make_autopay_active(workspace)

    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly", "payment_mode": "one_time"}
    )

    body = error(response, 409)
    assert body["code"] == "subscription_active"
    assert body["message"] == services.SubscriptionAlreadyActive.default_detail
    assert fake_razorpay.calls == []


@pytest.mark.parametrize("make_prepaid", [make_razorpay_prepaid_active, make_cashfree_active])
def test_autopay_waits_for_the_prepaid_period_to_end(
    auth_client, workspace, profile, fake_razorpay, make_prepaid
):
    make_prepaid(workspace)

    response = auth_client().post(
        CHECKOUT, {"plan_id": "growth", "interval": "monthly", "payment_mode": "autopay"}
    )

    body = error(response, 409)
    assert (body["code"], body["message"]) == ("subscription_active", PREPAID_MESSAGE)
    assert fake_razorpay.calls == []


@pytest.mark.parametrize("make_prepaid", [make_razorpay_prepaid_active, make_cashfree_active])
def test_an_active_prepaid_plan_may_pay_once_again(
    auth_client, workspace, profile, fake_razorpay, make_prepaid
):
    make_prepaid(workspace)

    assert pay_once(auth_client, "pro", "annual")["order_id"] == "order_fake000001"


def test_autopay_after_a_prepaid_period_ends_clears_prepaid(
    auth_client, client, workspace, profile, fake_razorpay
):
    expired = make_razorpay_prepaid_active(workspace, days_left=-1)
    expired.status = "expired"
    expired.save()
    subscription_id = (
        auth_client()
        .post(CHECKOUT, {"plan_id": "pro", "interval": "monthly"}, format="json")
        .json()["subscription_id"]
    )
    now = timezone.now()

    post_webhook(
        client,
        subscription_event(
            "subscription.activated",
            subscription_id,
            current_start=ts(now),
            current_end=ts(now + timedelta(days=30)),
        ),
    )

    body = auth_client().get(SUBSCRIPTION).json()
    assert (body["status"], body["plan"]["id"]) == ("active", "pro")
    assert (body["provider"], body["payment_mode"], body["auto_renews"]) == (
        "razorpay",
        "autopay",
        True,
    )
    assert Subscription.objects.get(workspace=workspace).prepaid is False


def test_cancelling_an_autopay_checkout_after_a_prepaid_plan_cancels_it_at_razorpay(
    auth_client, workspace, profile, fake_razorpay
):
    expired = make_razorpay_prepaid_active(workspace, days_left=-1)
    expired.status = "expired"
    expired.save()
    subscription_id = (
        auth_client()
        .post(CHECKOUT, {"plan_id": "pro", "interval": "monthly"}, format="json")
        .json()["subscription_id"]
    )

    response = auth_client().post(CANCEL, {"at_period_end": False}, format="json")

    assert response.status_code == 200, response.content
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": subscription_id, "at_cycle_end": False}
    ]
    assert Subscription.objects.get(workspace=workspace).razorpay_subscription_id is None


# --- Verify ---------------------------------------------------------------------------------


def test_verify_paid_order_activates_a_prepaid_plan(auth_client, workspace, profile, fake_razorpay):
    order_id = paid_order(auth_client, fake_razorpay)

    response = auth_client().post(VERIFY, verify_body(order_id), format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["status"], body["plan"]["id"], body["interval"]) == ("active", "growth", "monthly")
    assert (body["provider"], body["payment_mode"], body["auto_renews"]) == (
        "razorpay",
        "one_time",
        False,
    )
    subscription = Subscription.objects.get(workspace=workspace)
    assert subscription.prepaid is True
    assert subscription.razorpay_subscription_id is None
    now = timezone.now()
    assert approx(subscription.current_period_start, now)
    assert approx(subscription.current_period_end, now + timedelta(days=30))
    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.payment_id, invoice.payment_provider) == ("pay_once0001", "razorpay")
    assert (invoice.status, invoice.total_paise) == ("paid", GROWTH_MONTHLY_TOTAL)
    assert (invoice.period_start, invoice.period_end) == (
        subscription.current_period_start,
        subscription.current_period_end,
    )
    order = BillingOrder.objects.get(order_id=order_id)
    assert (order.status, order.payment_id) == ("paid", "pay_once0001")
    assert order.period_end == subscription.current_period_end


def test_verify_keys_the_invoice_on_the_captured_payment(
    auth_client, workspace, profile, fake_razorpay
):
    order_id = pay_once(auth_client)["order_id"]
    fake_razorpay.fail_order_payment(order_id, payment_id="pay_failed01")
    fake_razorpay.pay_order(order_id, payment_id="pay_good01")

    response = auth_client().post(VERIFY, verify_body(order_id, "pay_failed01"), format="json")

    assert response.status_code == 200, response.content
    assert Invoice.objects.get(workspace=workspace).payment_id == "pay_good01"


def test_verify_unpaid_order_is_not_completed(auth_client, workspace, profile, fake_razorpay):
    order_id = pay_once(auth_client)["order_id"]
    fake_razorpay.fail_order_payment(order_id)

    response = auth_client().post(VERIFY, verify_body(order_id), format="json")

    assert error(response, 409)["code"] == "payment_not_completed"
    assert BillingOrder.objects.get(order_id=order_id).status == "created"
    assert Subscription.objects.get(workspace=workspace).status == "trialing"
    assert not Invoice.objects.exists()


@pytest.mark.parametrize("tamper", ["signature", "order", "payment"])
def test_verify_rejects_bad_signatures(auth_client, workspace, profile, fake_razorpay, tamper):
    order_id = paid_order(auth_client, fake_razorpay)
    body = verify_body(order_id)
    if tamper == "signature":
        body["razorpay_signature"] = order_signature("pay_once0001", order_id, secret="wrong")
    elif tamper == "order":
        body["razorpay_signature"] = order_signature("pay_once0001", "order_other")
    else:
        body["razorpay_payment_id"] = "pay_other"

    response = auth_client().post(VERIFY, body, format="json")

    assert error(response, 400)["code"] == "payment_verification_failed"
    assert Subscription.objects.get(workspace=workspace).status == "trialing"
    assert fake_razorpay.calls_to("fetch_order") == []


def test_verify_another_workspaces_order_fails(auth_client, workspace, profile, fake_razorpay):
    other = WorkspaceFactory()
    entity = fake_razorpay.create_order(amount=100, currency="INR", receipt="r", notes={})
    BillingOrder.objects.create(
        workspace=other,
        provider="razorpay",
        order_id=entity["id"],
        plan_id="growth",
        interval="monthly",
        amount_paise=100,
    )
    fake_razorpay.pay_order(entity["id"])

    response = auth_client().post(VERIFY, verify_body(entity["id"]), format="json")

    assert error(response, 400)["code"] == "payment_verification_failed"
    assert BillingOrder.objects.get(order_id=entity["id"]).status == "created"


def test_verify_a_cashfree_order_id_as_razorpay_fails(auth_client, workspace, profile):
    BillingOrder.objects.create(
        workspace=workspace,
        provider="cashfree",
        order_id="upc_cashfree1",
        plan_id="growth",
        interval="monthly",
        amount_paise=100,
    )

    response = auth_client().post(VERIFY, verify_body("upc_cashfree1"), format="json")

    assert error(response, 400)["code"] == "payment_verification_failed"


def test_verify_reports_razorpay_outages(auth_client, profile, fake_razorpay):
    order_id = paid_order(auth_client, fake_razorpay)
    fake_razorpay.fail_with = RazorpayError("Gateway down", status_code=503)

    response = auth_client().post(VERIFY, verify_body(order_id), format="json")

    assert error(response, 503)["code"] == "upstream_unavailable"


def test_verify_an_already_paid_order_is_idempotent(auth_client, workspace, profile, fake_razorpay):
    order_id = paid_order(auth_client, fake_razorpay)
    first = auth_client().post(VERIFY, verify_body(order_id), format="json")
    fake_razorpay.calls.clear()

    second = auth_client().post(VERIFY, verify_body(order_id), format="json")

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["current_period_end"] == first.json()["current_period_end"]
    assert Invoice.objects.filter(workspace=workspace).count() == 1
    assert fake_razorpay.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"razorpay_payment_id": "pay_1", "razorpay_order_id": "order_1"},
        {
            "razorpay_payment_id": "pay_1",
            "razorpay_order_id": "order_1",
            "razorpay_subscription_id": "sub_1",
            "razorpay_signature": "x",
        },
        {"order_id": "upc_1", "razorpay_order_id": "order_1"},
        {"razorpay_order_id": "order_1", "razorpay_signature": "x"},
    ],
)
def test_verify_rejects_mixed_or_partial_forms(auth_client, body):
    assert error(auth_client().post(VERIFY, body, format="json"), 400)["code"] == "invalid"


def test_verify_needs_the_owner(auth_client):
    response = auth_client(Role.ADMIN).post(VERIFY, verify_body("order_1"), format="json")

    assert error(response, 403)["code"] == "insufficient_role"


# --- Renewal --------------------------------------------------------------------------------


@pytest.mark.parametrize("make_prepaid", [make_razorpay_prepaid_active, make_cashfree_active])
def test_paying_again_for_the_same_plan_extends_the_period(
    auth_client, workspace, profile, fake_razorpay, make_prepaid
):
    active = make_prepaid(workspace, days_left=3)
    active.cancel_at_period_end = True
    active.save()
    start, end = active.current_period_start, active.current_period_end
    order_id = paid_order(auth_client, fake_razorpay)

    auth_client().post(VERIFY, verify_body(order_id), format="json")

    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.provider, subscription.prepaid) == ("razorpay", True)
    assert subscription.current_period_start == start
    assert subscription.current_period_end == end + timedelta(days=30)
    assert subscription.cancel_at_period_end is False
    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.period_start, invoice.period_end) == (end, end + timedelta(days=30))


def test_changing_plan_starts_a_new_period(auth_client, workspace, profile, fake_razorpay):
    make_razorpay_prepaid_active(workspace, plan="growth", interval="monthly", days_left=20)
    order_id = paid_order(auth_client, fake_razorpay, plan_id="pro", interval="annual")

    auth_client().post(VERIFY, verify_body(order_id), format="json")

    subscription = Subscription.objects.get(workspace=workspace)
    now = timezone.now()
    assert (subscription.plan_id, subscription.interval) == ("pro", "annual")
    assert approx(subscription.current_period_start, now)
    assert approx(subscription.current_period_end, now + timedelta(days=365))


def test_paying_once_replaces_an_open_autopay_checkout(
    auth_client, workspace, profile, fake_razorpay, django_capture_on_commit_callbacks
):
    subscription_id = (
        auth_client()
        .post(CHECKOUT, {"plan_id": "pro", "interval": "monthly"}, format="json")
        .json()["subscription_id"]
    )
    order_id = paid_order(auth_client, fake_razorpay)

    with django_capture_on_commit_callbacks(execute=True):
        auth_client().post(VERIFY, verify_body(order_id), format="json")

    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.status, subscription.razorpay_subscription_id) == ("active", None)
    assert subscription.payment_mode == "one_time"
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": subscription_id, "at_cycle_end": False}
    ]


# --- order.paid webhook ---------------------------------------------------------------------


def test_order_paid_webhook_fulfils_the_order(auth_client, client, workspace, profile):
    order_id = pay_once(auth_client)["order_id"]
    paid_at = timezone.now() - timedelta(minutes=2)

    response = post_webhook(
        client,
        order_paid_event(order_id, GROWTH_MONTHLY_TOTAL, created_at=ts(paid_at)),
        event_id="evt_order1",
    )

    assert response.json() == {"status": "processed"}
    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.status, subscription.provider, subscription.prepaid) == (
        "active",
        "razorpay",
        True,
    )
    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.payment_id, invoice.payment_provider) == ("pay_order0001", "razorpay")
    order = BillingOrder.objects.get(order_id=order_id)
    assert (order.status, order.payment_id) == ("paid", "pay_order0001")
    assert approx(order.paid_at, paid_at, seconds=2)


def test_order_paid_retries_and_repeats_fulfil_once(auth_client, client, workspace, profile):
    order_id = pay_once(auth_client)["order_id"]
    payload = order_paid_event(order_id, GROWTH_MONTHLY_TOTAL)

    first = post_webhook(client, payload, event_id="evt_order1")
    retry = post_webhook(client, payload, event_id="evt_order1")
    repeat = post_webhook(client, payload, event_id="evt_order2")

    assert [r.json()["status"] for r in (first, retry, repeat)] == [
        "processed",
        "duplicate",
        "duplicate",
    ]
    assert RazorpayEvent.objects.count() == 2
    assert Invoice.objects.filter(workspace=workspace).count() == 1
    end = BillingOrder.objects.get(order_id=order_id).period_end
    assert Subscription.objects.get(workspace=workspace).current_period_end == end


def test_verify_and_webhook_fulfil_once(auth_client, client, workspace, profile, fake_razorpay):
    order_id = paid_order(auth_client, fake_razorpay, payment_id="pay_order0001")

    post_webhook(client, order_paid_event(order_id, GROWTH_MONTHLY_TOTAL))
    response = auth_client().post(VERIFY, verify_body(order_id, "pay_order0001"), format="json")

    assert response.status_code == 200, response.content
    assert Invoice.objects.filter(workspace=workspace).count() == 1
    assert fake_razorpay.calls_to("fetch_order") == []


def test_order_paid_amount_mismatch_is_ignored(auth_client, client, workspace, profile, caplog):
    order_id = pay_once(auth_client)["order_id"]

    response = post_webhook(client, order_paid_event(order_id, 100))

    assert response.json() == {"status": "ignored"}
    assert BillingOrder.objects.get(order_id=order_id).status == "created"
    assert Subscription.objects.get(workspace=workspace).status == "trialing"
    assert order_id in caplog.text


def test_order_paid_for_an_unknown_order_is_ignored(client):
    response = post_webhook(client, order_paid_event("order_unknown1", 100))

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert not Invoice.objects.exists()


def test_failed_order_payment_is_logged(auth_client, client, workspace, profile, caplog):
    order_id = pay_once(auth_client)["order_id"]
    payload = {
        "entity": "event",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {"entity": {"id": "pay_fail9", "status": "failed", "order_id": order_id}}
        },
    }

    response = post_webhook(client, payload)

    assert response.json() == {"status": "logged"}
    assert "pay_fail9" in caplog.text
    assert f"billing order {order_id}" in caplog.text
    assert BillingOrder.objects.get(order_id=order_id).status == "created"


# --- Cancel, expiry and reminders for Razorpay prepaid plans --------------------------------


@pytest.mark.parametrize(("at_period_end", "status"), [(True, "active"), (False, "cancelled")])
def test_cancelling_a_razorpay_prepaid_plan_never_calls_razorpay(
    auth_client, workspace, fake_razorpay, at_period_end, status
):
    make_razorpay_prepaid_active(workspace)

    body = auth_client().post(CANCEL, {"at_period_end": at_period_end}, format="json").json()

    assert (body["status"], body["cancel_at_period_end"]) == (status, at_period_end)
    assert body["auto_renews"] is False
    assert fake_razorpay.calls == []


def test_expire_prepaid_ends_razorpay_prepaid_plans_only(workspace):
    make_razorpay_prepaid_active(workspace, days_left=-0.01)
    autopay_ws = WorkspaceFactory()
    autopay = make_autopay_active(autopay_ws)
    Subscription.objects.filter(pk=autopay.pk).update(
        current_period_end=timezone.now() - timedelta(days=1)
    )

    assert services.expire_prepaid() == 1

    assert Subscription.objects.get(workspace=workspace).status == "expired"
    # Auto-pay subscriptions end through Razorpay's webhooks, not this task.
    assert Subscription.objects.get(workspace=autopay_ws).status == "active"


def test_renewal_reminders_cover_razorpay_prepaid_plans(
    workspace, user, profile, django_capture_on_commit_callbacks
):
    subscription = make_razorpay_prepaid_active(workspace, days_left=30)
    autopay = make_autopay_active(WorkspaceFactory())
    Subscription.objects.filter(pk=autopay.pk).update(
        current_period_end=subscription.current_period_end
    )
    week_before = subscription.current_period_end - timedelta(days=7)

    with django_capture_on_commit_callbacks(execute=True):
        sent = services.send_renewal_reminders(now=week_before)

    assert sent == 1
    assert sorted(message.to[0] for message in mail.outbox) == sorted([user.email, profile.email])


# --- payment_mode and the data migration ----------------------------------------------------


def test_subscription_reports_the_payment_mode(auth_client, workspace):
    def mode():
        body = auth_client().get(SUBSCRIPTION).json()
        return body["payment_mode"], body["auto_renews"]

    assert mode() == (None, False)
    make_autopay_active(workspace)
    assert mode() == ("autopay", True)
    make_razorpay_prepaid_active(workspace)
    assert mode() == ("one_time", False)
    make_cashfree_active(workspace)
    assert mode() == ("one_time", False)


def test_payment_mode_values_match_the_contract_enum():
    assert tuple(PaymentMode.values) == PAYMENT_MODES


def test_the_migration_marks_cashfree_plans_prepaid():
    migration = importlib.import_module("apps.billing.migrations.0006_prepaid_plans")
    cashfree = services.get_subscription(WorkspaceFactory())
    razorpay = services.get_subscription(WorkspaceFactory())
    trial = services.get_subscription(WorkspaceFactory())
    Subscription.objects.filter(pk=cashfree.pk).update(provider="cashfree", prepaid=False)
    Subscription.objects.filter(pk=razorpay.pk).update(provider="razorpay", prepaid=False)

    migration.mark_cashfree_prepaid(django_apps, None)
    migration.mark_cashfree_prepaid(django_apps, None)

    prepaid = dict(Subscription.objects.values_list("pk", "prepaid"))
    assert (prepaid[cashfree.pk], prepaid[razorpay.pk], prepaid[trial.pk]) == (True, False, False)
