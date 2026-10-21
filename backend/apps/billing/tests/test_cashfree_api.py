"""Cashfree prepaid billing (docs/contracts/billing-cashfree.md): checkout, verify, fulfilment,
the signed webhook, cancellation, expiry and renewal reminders."""

import json
import re
from datetime import datetime, timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.billing import services
from apps.billing.cashfree import CashfreeError, override_cashfree_client
from apps.billing.models import BillingOrder, BillingProfile, Invoice, Subscription
from apps.billing.tests.helpers import (
    KARNATAKA_PROFILE,
    MAHARASHTRA_PROFILE,
    cashfree_payment_event,
    cashfree_signature,
    make_active,
    make_cashfree_active,
    post_cashfree_webhook,
)
from apps.tenants.factories import WorkspaceFactory
from common.roles import Role

pytestmark = pytest.mark.django_db

BASE = "/api/v1/billing"
SUBSCRIPTION = f"{BASE}/subscription/"
CHECKOUT = f"{BASE}/subscription/checkout/"
VERIFY = f"{BASE}/subscription/verify/"
CANCEL = f"{BASE}/subscription/cancel/"
PROFILE = f"{BASE}/billing-profile/"

GROWTH_MONTHLY_PAISE = 249900
GROWTH_MONTHLY_TOTAL = 294882  # + 18% GST (44982)
PHONE = "+919876543210"


def error(response, status: int) -> dict:
    assert response.status_code == status, response.content
    return response.json()["error"]


@pytest.fixture
def profile(workspace):
    return BillingProfile.objects.create(workspace=workspace, phone=PHONE, **MAHARASHTRA_PROFILE)


def checkout(auth_client, plan_id="growth", interval="monthly") -> dict:
    response = auth_client().post(
        CHECKOUT, {"plan_id": plan_id, "interval": interval}, format="json"
    )
    assert response.status_code == 200, response.content
    return response.json()


def approx(moment: datetime, expected: datetime, seconds: int = 60) -> bool:
    return abs((moment - expected).total_seconds()) < seconds


# --- Checkout -------------------------------------------------------------------------------


def test_checkout_creates_a_gst_inclusive_cashfree_order(
    auth_client, workspace, profile, fake_cashfree
):
    session = checkout(auth_client)

    order_id = session["order_id"]
    assert re.fullmatch(r"upc_[0-9a-f]{32}", order_id)
    assert session == {
        "provider": "cashfree",
        "payment_mode": "one_time",
        "name": "UpChatz",
        "description": "Growth plan: ₹2,499 + 18% GST per month",
        "prefill": {"name": MAHARASHTRA_PROFILE["legal_name"], "email": profile.email},
        "key_id": None,
        "subscription_id": None,
        "order_id": order_id,
        "payment_session_id": "session_fake000001",
        "mode": "sandbox",
        "amount_paise": GROWTH_MONTHLY_TOTAL,
    }
    [call] = fake_cashfree.calls_to("create_order")
    body = call["body"]
    assert body["order_amount"] == 2948.82
    assert body["order_currency"] == "INR"
    assert body["customer_details"] == {
        "customer_id": workspace.pk.hex,
        "customer_phone": "9876543210",
        "customer_email": "accounts@asha.example",
        "customer_name": "Asha Traders Private Limited",
    }
    assert body["order_meta"] == {
        "return_url": f"http://testserver-frontend/app/w/{workspace.pk}/billing"
        f"?cf_order_id={order_id}",
        "notify_url": "https://api.testserver/webhooks/cashfree/billing/",
    }
    assert body["order_note"] == session["description"]
    assert body["order_tags"] == {
        "workspace_id": str(workspace.pk),
        "plan": "growth",
        "interval": "monthly",
    }
    expiry = datetime.fromisoformat(body["order_expiry_time"])
    assert body["order_expiry_time"].endswith("+05:30")
    assert approx(expiry, timezone.now() + timedelta(hours=1))

    order = BillingOrder.objects.get(order_id=order_id)
    assert (order.workspace_id, order.plan_id, order.interval) == (
        workspace.pk,
        "growth",
        "monthly",
    )
    assert (order.amount_paise, order.status) == (GROWTH_MONTHLY_TOTAL, "created")
    # The subscription only changes once the order is paid.
    assert Subscription.objects.get(workspace=workspace).status == "trialing"


def test_checkout_amount_matches_the_intra_state_invoice(auth_client, workspace, fake_cashfree):
    BillingProfile.objects.create(workspace=workspace, phone=PHONE, **KARNATAKA_PROFILE)

    session = checkout(auth_client, "pro", "annual")

    expected = services.checkout_total_paise(
        services.Plan.objects.get(slug="pro"), "annual", KARNATAKA_PROFILE["state_code"]
    )
    assert session["amount_paise"] == expected
    assert fake_cashfree.calls_to("create_order")[0]["body"]["order_amount"] == expected / 100


def test_without_gst_the_plan_price_is_charged_and_invoiced(
    auth_client, workspace, profile, fake_cashfree, settings
):
    settings.BILLING_GST_ENABLED = False
    assert auth_client().get(SUBSCRIPTION).json()["gst_rate_percent"] == 0

    session = checkout(auth_client)

    assert session["description"] == "Growth plan: ₹2,499 per month"
    assert session["amount_paise"] == GROWTH_MONTHLY_PAISE
    assert fake_cashfree.calls_to("create_order")[0]["body"]["order_amount"] == 2499.0
    fake_cashfree.pay(session["order_id"], cf_payment_id="885000777")
    assert auth_client().post(VERIFY, {"order_id": session["order_id"]}).status_code == 200
    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.gst_rate_percent, invoice.subtotal_paise, invoice.total_paise) == (
        0,
        GROWTH_MONTHLY_PAISE,
        GROWTH_MONTHLY_PAISE,
    )
    assert invoice.cgst_paise == invoice.sgst_paise == invoice.igst_paise == 0


def test_subscription_reports_the_gst_rate(auth_client):
    assert auth_client().get(SUBSCRIPTION).json()["gst_rate_percent"] == 18


def test_checkout_needs_a_phone_on_the_billing_profile(auth_client, workspace, fake_cashfree):
    BillingProfile.objects.create(workspace=workspace, **MAHARASHTRA_PROFILE)

    response = auth_client().post(CHECKOUT, {"plan_id": "growth", "interval": "monthly"})

    body = error(response, 409)
    assert body["code"] == "billing_profile_required"
    assert "phone" in body["message"]
    assert fake_cashfree.calls == []
    assert not BillingOrder.objects.exists()


def test_checkout_reports_cashfree_outages(auth_client, profile, fake_cashfree):
    fake_cashfree.fail_with = CashfreeError("Cashfree returned HTTP 502.", status_code=502)

    response = auth_client().post(CHECKOUT, {"plan_id": "growth", "interval": "monthly"})

    assert error(response, 503)["code"] == "upstream_unavailable"
    assert not BillingOrder.objects.exists()


def test_checkout_without_cashfree_keys_is_unavailable(auth_client, profile, settings):
    settings.BILLING_CASHFREE_APP_ID = ""
    with override_cashfree_client(None):
        response = auth_client().post(CHECKOUT, {"plan_id": "growth", "interval": "monthly"})

    assert error(response, 503)["code"] == "upstream_unavailable"


def test_checkout_is_allowed_while_a_cashfree_plan_is_active(auth_client, workspace, profile):
    make_cashfree_active(workspace)

    assert checkout(auth_client)["provider"] == "cashfree"


def test_checkout_is_refused_while_a_razorpay_subscription_is_active(
    auth_client, workspace, profile, fake_cashfree
):
    make_active(workspace)

    response = auth_client().post(CHECKOUT, {"plan_id": "growth", "interval": "monthly"})

    assert error(response, 409)["code"] == "subscription_active"
    assert fake_cashfree.calls == []


# --- Subscription and profile shapes --------------------------------------------------------


def test_subscription_reports_providers(auth_client, workspace, settings):
    trial = auth_client().get(SUBSCRIPTION).json()
    assert (trial["provider"], trial["auto_renews"], trial["checkout_provider"]) == (
        None,
        False,
        "cashfree",
    )

    make_active(workspace)
    settings.BILLING_PROVIDER = "razorpay"
    razorpay = auth_client().get(SUBSCRIPTION).json()
    assert (razorpay["auto_renews"], razorpay["checkout_provider"]) == (True, "razorpay")

    make_cashfree_active(workspace)
    prepaid = auth_client().get(SUBSCRIPTION).json()
    assert (prepaid["provider"], prepaid["auto_renews"]) == ("cashfree", False)


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("98765 43210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("+14155552671", "+14155552671"),
        ("", ""),
    ],
)
def test_billing_profile_phone_is_stored_as_e164(auth_client, workspace, raw, stored):
    response = auth_client().patch(PROFILE, {**MAHARASHTRA_PROFILE, "phone": raw}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["phone"] == stored
    assert BillingProfile.objects.get(workspace=workspace).phone == stored


@pytest.mark.parametrize("raw", ["12345", "phone", "+1 555"])
def test_billing_profile_rejects_bad_phones(auth_client, raw):
    response = auth_client().patch(PROFILE, {"phone": raw}, format="json")

    assert "phone" in error(response, 400)["details"]


# --- Verify and fulfilment ------------------------------------------------------------------


def test_verify_paid_order_activates_the_plan_and_issues_the_invoice(
    auth_client, workspace, profile, fake_cashfree
):
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.pay(order_id, cf_payment_id="885000123")

    response = auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["status"], body["plan"]["id"], body["interval"]) == ("active", "growth", "monthly")
    assert (body["provider"], body["auto_renews"]) == ("cashfree", False)
    subscription = Subscription.objects.get(workspace=workspace)
    now = timezone.now()
    assert approx(subscription.current_period_start, now)
    assert approx(subscription.current_period_end, now + timedelta(days=30))
    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.payment_id, invoice.payment_provider) == ("885000123", "cashfree")
    assert (invoice.status, invoice.total_paise) == ("paid", GROWTH_MONTHLY_TOTAL)
    assert (invoice.period_start, invoice.period_end) == (
        subscription.current_period_start,
        subscription.current_period_end,
    )
    order = BillingOrder.objects.get(order_id=order_id)
    assert (order.status, order.payment_id, order.payment_session_id) == (
        "paid",
        "885000123",
        "",
    )
    assert order.period_end == subscription.current_period_end


@pytest.mark.parametrize(("remote", "local"), [("ACTIVE", "created"), ("EXPIRED", "expired")])
def test_verify_unpaid_order_is_not_completed(
    auth_client, workspace, profile, fake_cashfree, remote, local
):
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.set_status(order_id, remote)

    response = auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    body = error(response, 409)
    assert body["code"] == "payment_not_completed"
    assert body["message"] == "The payment wasn't completed. You haven't been charged."
    assert BillingOrder.objects.get(order_id=order_id).status == local
    assert Subscription.objects.get(workspace=workspace).status == "trialing"
    assert not Invoice.objects.exists()


def test_verify_another_workspaces_order_fails(auth_client, workspace, profile, fake_cashfree):
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.pay(order_id)
    other = WorkspaceFactory()
    stranger = auth_client(workspace=other)

    response = stranger.post(VERIFY, {"order_id": order_id}, format="json")
    unknown = auth_client().post(VERIFY, {"order_id": "upc_unknown"}, format="json")

    assert error(response, 400)["code"] == "payment_verification_failed"
    assert error(unknown, 400)["code"] == "payment_verification_failed"
    assert BillingOrder.objects.get(order_id=order_id).status == "created"


def test_verify_reports_cashfree_outages(auth_client, profile, fake_cashfree):
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.fail_with = CashfreeError("timeout", retryable=True)

    response = auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    assert error(response, 503)["code"] == "upstream_unavailable"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"order_id": "upc_1", "razorpay_payment_id": "pay_1"},
        {"razorpay_payment_id": "pay_1", "razorpay_subscription_id": "sub_1"},
    ],
)
def test_verify_needs_order_id_or_all_razorpay_fields(auth_client, body):
    assert error(auth_client().post(VERIFY, body, format="json"), 400)["code"] == "invalid"


def test_verify_needs_the_owner(auth_client):
    response = auth_client(Role.ADMIN).post(VERIFY, {"order_id": "upc_1"}, format="json")

    assert error(response, 403)["code"] == "insufficient_role"


def test_renewal_on_the_same_plan_extends_the_period(
    auth_client, workspace, profile, fake_cashfree
):
    active = make_cashfree_active(workspace, days_left=3)
    active.cancel_at_period_end = True
    active.save()
    start, end = active.current_period_start, active.current_period_end
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.pay(order_id)

    auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    subscription = Subscription.objects.get(workspace=workspace)
    assert subscription.current_period_start == start
    assert subscription.current_period_end == end + timedelta(days=30)
    assert subscription.cancel_at_period_end is False
    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.period_start, invoice.period_end) == (end, end + timedelta(days=30))


def test_plan_change_starts_now(auth_client, workspace, profile, fake_cashfree):
    make_cashfree_active(workspace, plan="growth", interval="monthly", days_left=20)
    order_id = checkout(auth_client, "pro", "annual")["order_id"]
    fake_cashfree.pay(order_id)

    auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    subscription = Subscription.objects.get(workspace=workspace)
    now = timezone.now()
    assert (subscription.plan_id, subscription.interval) == ("pro", "annual")
    assert approx(subscription.current_period_start, now)
    assert approx(subscription.current_period_end, now + timedelta(days=365))


def test_paying_after_expiry_starts_a_new_period(auth_client, workspace, profile, fake_cashfree):
    expired = make_cashfree_active(workspace, days_left=-2)
    expired.status = "expired"
    expired.save()
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.pay(order_id)

    auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    subscription = Subscription.objects.get(workspace=workspace)
    assert subscription.status == "active"
    assert approx(subscription.current_period_end, timezone.now() + timedelta(days=30))


def test_paying_replaces_an_open_razorpay_checkout(
    auth_client,
    workspace,
    profile,
    fake_cashfree,
    fake_razorpay,
    django_capture_on_commit_callbacks,
):
    entity = fake_razorpay.create_subscription(
        plan_id="plan_test_growth_monthly", total_count=120, notes={}
    )
    subscription = services.get_subscription(workspace)
    subscription.razorpay_subscription_id = entity["id"]
    subscription.status = "pending"
    subscription.save()
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.pay(order_id)

    with django_capture_on_commit_callbacks(execute=True):
        auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    subscription.refresh_from_db()
    assert (subscription.status, subscription.razorpay_subscription_id) == ("active", None)
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": entity["id"], "at_cycle_end": False}
    ]


def test_verify_and_webhook_fulfil_once(auth_client, client, workspace, profile, fake_cashfree):
    order_id = checkout(auth_client)["order_id"]
    fake_cashfree.pay(order_id, cf_payment_id="885000777")

    first = auth_client().post(VERIFY, {"order_id": order_id}, format="json")
    end = Subscription.objects.get(workspace=workspace).current_period_end
    hook = post_cashfree_webhook(client, cashfree_payment_event(order_id, 2948.82))
    again = auth_client().post(VERIFY, {"order_id": order_id}, format="json")

    assert (first.status_code, again.status_code) == (200, 200)
    assert (hook.status_code, hook.json()) == (200, {"status": "duplicate"})
    assert Invoice.objects.filter(workspace=workspace).count() == 1
    assert Subscription.objects.get(workspace=workspace).current_period_end == end
    assert fake_cashfree.calls_to("fetch_order") == [{"order_id": order_id}]


# --- Webhook --------------------------------------------------------------------------------


def test_webhook_fulfils_a_paid_order(auth_client, client, workspace, profile):
    order_id = checkout(auth_client)["order_id"]

    response = post_cashfree_webhook(
        client, cashfree_payment_event(order_id, 2948.82, cf_payment_id=885000901)
    )

    assert (response.status_code, response.json()) == (200, {"status": "processed"})
    assert Subscription.objects.get(workspace=workspace).status == "active"
    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.payment_id, invoice.payment_provider) == ("885000901", "cashfree")
    order = BillingOrder.objects.get(order_id=order_id)
    assert order.paid_at == datetime.fromisoformat("2026-10-10T12:00:05+05:30")


@pytest.mark.parametrize("signature", ["bm90IHRoZSBzaWduYXR1cmU=", "", False])
def test_webhook_rejects_bad_or_missing_signatures(auth_client, client, profile, signature):
    order_id = checkout(auth_client)["order_id"]

    response = post_cashfree_webhook(
        client, cashfree_payment_event(order_id, 2948.82), signature=signature
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_signature"
    assert not Invoice.objects.exists()


def test_webhook_signed_with_another_secret_is_rejected(auth_client, client, profile):
    order_id = checkout(auth_client)["order_id"]
    payload = cashfree_payment_event(order_id, 2948.82)

    body = json.dumps(payload).encode()
    response = post_cashfree_webhook(
        client, payload, signature=cashfree_signature(body, "1760078407", secret="other")
    )

    assert response.status_code == 400


def test_webhook_amount_mismatch_is_ignored(auth_client, client, workspace, profile):
    order_id = checkout(auth_client)["order_id"]

    response = post_cashfree_webhook(client, cashfree_payment_event(order_id, 1.00))

    assert (response.status_code, response.json()) == (200, {"status": "ignored"})
    assert Subscription.objects.get(workspace=workspace).status == "trialing"
    assert BillingOrder.objects.get(order_id=order_id).status == "created"


def test_webhook_for_an_unknown_order_is_ignored(client):
    response = post_cashfree_webhook(client, cashfree_payment_event("upc_unknown", 10.0))

    assert (response.status_code, response.json()) == (200, {"status": "ignored"})


@pytest.mark.parametrize(
    ("event_type", "status", "outcome"),
    [
        ("PAYMENT_FAILED_WEBHOOK", "FAILED", "logged"),
        ("PAYMENT_USER_DROPPED_WEBHOOK", "USER_DROPPED", "logged"),
        ("PAYMENT_SUCCESS_WEBHOOK", "PENDING", "ignored"),
        ("REFUND_STATUS_WEBHOOK", "SUCCESS", "ignored"),
    ],
)
def test_webhook_other_events_change_nothing(
    auth_client, client, workspace, profile, event_type, status, outcome
):
    order_id = checkout(auth_client)["order_id"]
    payload = cashfree_payment_event(
        order_id, 2948.82, event_type=event_type, payment_status=status
    )

    response = post_cashfree_webhook(client, payload)

    assert (response.status_code, response.json()) == (200, {"status": outcome})
    assert Subscription.objects.get(workspace=workspace).status == "trialing"


def test_webhook_rejects_non_json(client):
    body = b"not json"
    response = client.post(
        "/webhooks/cashfree/billing/",
        data=body,
        content_type="application/json",
        HTTP_X_WEBHOOK_TIMESTAMP="1",
        HTTP_X_WEBHOOK_SIGNATURE=cashfree_signature(body, "1"),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_payload"


# --- Cancel and expiry ----------------------------------------------------------------------


def test_cancel_at_period_end_then_expiry_cancels(auth_client, workspace, fake_razorpay):
    make_cashfree_active(workspace, days_left=2)

    body = auth_client().post(CANCEL, {"at_period_end": True}, format="json").json()
    assert (body["status"], body["cancel_at_period_end"]) == ("active", True)
    assert services.expire_prepaid() == 0

    assert services.expire_prepaid(now=timezone.now() + timedelta(days=3)) == 1
    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.status, subscription.cancel_at_period_end) == ("cancelled", False)
    assert fake_razorpay.calls == []


def test_cancel_immediately_needs_no_gateway(auth_client, workspace, fake_razorpay):
    make_cashfree_active(workspace)

    body = auth_client().post(CANCEL, {"at_period_end": False}, format="json").json()

    assert body["status"] == "cancelled"
    assert fake_razorpay.calls == []


def test_plain_period_end_expires(workspace):
    make_cashfree_active(workspace, days_left=-0.01)
    razorpay_ws = WorkspaceFactory()
    razorpay_sub = make_active(razorpay_ws)
    Subscription.objects.filter(pk=razorpay_sub.pk).update(
        current_period_end=timezone.now() - timedelta(days=1)
    )

    assert services.expire_prepaid() == 1

    assert Subscription.objects.get(workspace=workspace).status == "expired"
    # Razorpay subscriptions end through Razorpay's webhooks, not this task.
    assert Subscription.objects.get(workspace=razorpay_ws).status == "active"


def test_expire_prepaid_task(workspace):
    from apps.billing.tasks import expire_prepaid

    make_cashfree_active(workspace, days_left=-1)

    assert expire_prepaid.delay().get() == 1


# --- Renewal reminders ----------------------------------------------------------------------


def _remind(now, django_capture_on_commit_callbacks) -> int:
    with django_capture_on_commit_callbacks(execute=True):
        return services.send_renewal_reminders(now=now)


def test_renewal_reminders_go_out_once_at_7_and_1_days(
    workspace, user, profile, django_capture_on_commit_callbacks
):
    subscription = make_cashfree_active(workspace, days_left=30)
    end = subscription.current_period_end

    assert _remind(end - timedelta(days=10), django_capture_on_commit_callbacks) == 0
    assert mail.outbox == []

    week_before = end - timedelta(days=7)
    assert _remind(week_before, django_capture_on_commit_callbacks) == 1
    assert _remind(week_before + timedelta(days=1), django_capture_on_commit_callbacks) == 0
    assert sorted(message.to[0] for message in mail.outbox) == sorted([user.email, profile.email])
    reminder = mail.outbox[0]
    assert "Growth" in reminder.subject
    assert f"/app/w/{workspace.pk}/billing/plans" in reminder.body
    subscription.refresh_from_db()
    assert subscription.renewal_reminder_key == f"{end.isoformat()}:7"

    mail.outbox.clear()
    day_before = end - timedelta(hours=20)
    assert _remind(day_before, django_capture_on_commit_callbacks) == 1
    assert _remind(day_before + timedelta(hours=2), django_capture_on_commit_callbacks) == 0
    assert len(mail.outbox) == 2
    subscription.refresh_from_db()
    assert subscription.renewal_reminder_key == f"{end.isoformat()}:1"


def test_no_reminders_for_cancelled_or_razorpay_plans(
    workspace, profile, django_capture_on_commit_callbacks
):
    subscription = make_cashfree_active(workspace, days_left=3)
    subscription.cancel_at_period_end = True
    subscription.save()
    other = WorkspaceFactory()
    razorpay_sub = make_active(other)
    Subscription.objects.filter(pk=razorpay_sub.pk).update(
        current_period_end=timezone.now() + timedelta(days=3)
    )

    assert _remind(timezone.now(), django_capture_on_commit_callbacks) == 0
    assert mail.outbox == []


@pytest.mark.parametrize(
    ("days_left", "expected"),
    [(30, None), (8, None), (7, 7), (2, 7), (1, 1), (0, 1)],
)
def test_renewal_reminder_days(days_left, expected):
    now = datetime.fromisoformat("2026-10-10T09:00:00+05:30")

    assert services.renewal_reminder_days(now + timedelta(days=days_left), now) == expected
