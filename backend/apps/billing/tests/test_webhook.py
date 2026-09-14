"""Razorpay webhook: signature, idempotency, state transitions and invoices."""

import json
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.billing import invoices, services, webhooks
from apps.billing.models import BillingProfile, Invoice, RazorpayEvent, Subscription
from apps.billing.tests.helpers import (
    KARNATAKA_PROFILE,
    MAHARASHTRA_PROFILE,
    make_active,
    post_webhook,
    subscription_event,
    ts,
    webhook_signature,
)

pytestmark = pytest.mark.django_db

URL = "/webhooks/razorpay/"
CHECKOUT_ID = "sub_hook0001"


@pytest.fixture
def checkout(workspace):
    """A trialing workspace with an open checkout for Pro monthly."""
    subscription = services.get_subscription(workspace)
    subscription.status = "pending"
    subscription.razorpay_subscription_id = CHECKOUT_ID
    subscription.checkout_plan_id = "pro"
    subscription.checkout_interval = "monthly"
    subscription.save()
    return subscription


def reload(subscription) -> Subscription:
    return Subscription.objects.select_related("plan").get(pk=subscription.pk)


# --- Signature and delivery handling --------------------------------------------------------


def test_missing_or_invalid_signatures_are_rejected(client, checkout, caplog):
    payload = subscription_event("subscription.activated", CHECKOUT_ID)
    body = json.dumps(payload).encode()

    responses = [
        client.post(URL, data=body, content_type="application/json"),
        post_webhook(client, payload, signature="deadbeef"),
        post_webhook(client, payload, signature=webhook_signature(body, secret="wrong")),
    ]

    for response in responses:
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_signature"
    assert not RazorpayEvent.objects.exists()
    assert reload(checkout).status == "pending"
    assert "deadbeef" not in caplog.text
    assert settings.RAZORPAY_WEBHOOK_SECRET not in caplog.text


def test_a_tampered_body_is_rejected(client, checkout):
    body = json.dumps(subscription_event("subscription.activated", CHECKOUT_ID)).encode()
    signature = webhook_signature(body)

    response = client.post(
        URL,
        data=body.replace(b"activated", b"cancelled"),
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=signature,
    )

    assert response.status_code == 400


def test_invalid_json_is_rejected(client):
    body = b"not json"

    response = client.post(
        URL,
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=webhook_signature(body),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_payload"


def test_get_is_not_allowed(client):
    assert client.get(URL).status_code == 405


def test_unknown_subscriptions_are_acknowledged(client, checkout):
    response = post_webhook(
        client, subscription_event("subscription.activated", "sub_unknown"), event_id="evt_unknown"
    )

    assert response.status_code == 200
    assert response.json() == {"status": "unknown_subscription"}
    assert RazorpayEvent.objects.get(event_id="evt_unknown").processed_at is not None
    assert reload(checkout).status == "pending"


def test_unhandled_events_are_acknowledged(client):
    response = post_webhook(client, {"event": "order.paid", "payload": {}})

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_duplicate_event_ids_are_processed_once(client, checkout, monkeypatch):
    calls = []
    original = webhooks.process_event

    def counting(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(webhooks, "process_event", counting)
    payload = subscription_event("subscription.halted", CHECKOUT_ID)

    first = post_webhook(client, payload, event_id="evt_dup")
    second = post_webhook(client, payload, event_id="evt_dup")

    assert first.json() == {"status": "processed"}
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert len(calls) == 1
    assert RazorpayEvent.objects.filter(event_id="evt_dup").count() == 1


def test_deliveries_without_an_event_id_are_deduplicated_by_body(client, checkout):
    payload = subscription_event("subscription.halted", CHECKOUT_ID)

    first = post_webhook(client, payload, event_id=None)
    second = post_webhook(client, payload, event_id=None)

    assert (first.json()["status"], second.json()["status"]) == ("processed", "duplicate")


def test_processing_errors_roll_back_the_event_so_razorpay_retries(client, checkout, monkeypatch):
    def fail(*args):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(webhooks, "process_event", fail)

    with pytest.raises(RuntimeError):
        post_webhook(client, subscription_event("subscription.activated", CHECKOUT_ID))

    assert not RazorpayEvent.objects.exists()


# --- State transitions ----------------------------------------------------------------------


@pytest.mark.parametrize("event", ["subscription.authenticated", "subscription.activated"])
def test_activation_applies_the_plan_and_period(client, checkout, event):
    now = timezone.now()
    start, end = now - timedelta(minutes=1), now + timedelta(days=30)
    payload = subscription_event(
        event,
        CHECKOUT_ID,
        plan_id="plan_test_pro_monthly",
        current_start=ts(start),
        current_end=ts(end),
    )

    assert post_webhook(client, payload).status_code == 200

    subscription = reload(checkout)
    assert (subscription.status, subscription.plan_id, subscription.interval) == (
        "active",
        "pro",
        "monthly",
    )
    assert ts(subscription.current_period_start) == ts(start)
    assert ts(subscription.current_period_end) == ts(end)
    assert subscription.activated_at is not None
    assert (subscription.checkout_plan_id, subscription.checkout_interval) == (None, "")
    assert subscription.razorpay_customer_id == "cust_test1"


def test_activation_falls_back_to_the_checkout_plan(client, checkout):
    payload = subscription_event("subscription.activated", CHECKOUT_ID, plan_id="plan_other")

    post_webhook(client, payload)

    assert (reload(checkout).plan_id, reload(checkout).interval) == ("pro", "monthly")


def charged_payload(*, payment_id="pay_hook1", amount=707882) -> dict:
    now = timezone.now()
    payment = {
        "id": payment_id,
        "entity": "payment",
        "amount": amount,
        "currency": "INR",
        "status": "captured",
        "invoice_id": "inv_hook1",
    }
    return subscription_event(
        "subscription.charged",
        CHECKOUT_ID,
        plan_id="plan_test_pro_monthly",
        current_start=ts(now),
        current_end=ts(now + timedelta(days=30)),
        payment=payment,
    )


def test_charge_activates_and_issues_one_igst_invoice(client, workspace, checkout):
    BillingProfile.objects.create(workspace=workspace, **MAHARASHTRA_PROFILE)
    payload = charged_payload()

    first = post_webhook(client, payload, event_id="evt_charge_1")
    retry = post_webhook(client, payload, event_id="evt_charge_2")  # same payment, new event id

    assert (first.status_code, retry.status_code) == (200, 200)
    subscription = reload(checkout)
    assert (subscription.status, subscription.plan_id) == ("active", "pro")
    invoice = Invoice.objects.get(workspace=workspace)
    fiscal_year = invoices.financial_year(invoice.issued_at)
    assert invoice.number == invoices.format_invoice_number(fiscal_year, 1)
    assert invoice.status == "paid"
    assert (invoice.subtotal_paise, invoice.cgst_paise, invoice.sgst_paise) == (599900, 0, 0)
    assert (invoice.igst_paise, invoice.total_paise) == (107982, 707882)
    assert (invoice.razorpay_payment_id, invoice.razorpay_invoice_id) == ("pay_hook1", "inv_hook1")
    assert (invoice.sac_code, invoice.gst_rate_percent) == ("998314", 18)
    assert invoice.buyer["gstin"] == MAHARASHTRA_PROFILE["gstin"]
    assert invoice.buyer["state_name"] == "Maharashtra"
    assert invoice.seller["gstin"] == settings.BILLING_SELLER_GSTIN
    assert (invoice.plan_slug, invoice.subscription_id) == ("pro", subscription.pk)
    assert invoice.period_end > invoice.period_start


def test_same_state_buyer_invoice_splits_cgst_and_sgst(client, workspace, checkout):
    BillingProfile.objects.create(workspace=workspace, **KARNATAKA_PROFILE)

    post_webhook(client, charged_payload())

    invoice = Invoice.objects.get(workspace=workspace)
    assert (invoice.cgst_paise, invoice.sgst_paise, invoice.igst_paise) == (53991, 53991, 0)
    assert invoice.total_paise == 707882


def test_charge_amount_without_gst_is_flagged(client, workspace, checkout, caplog):
    BillingProfile.objects.create(workspace=workspace, **MAHARASHTRA_PROFILE)

    post_webhook(client, charged_payload(amount=599900))

    assert "includes GST" in caplog.text
    assert Invoice.objects.filter(workspace=workspace).count() == 1


@pytest.mark.parametrize(
    ("event", "status"), [("subscription.pending", "pending"), ("subscription.halted", "halted")]
)
def test_payment_retry_states(client, workspace, event, status):
    subscription = make_active(workspace)

    post_webhook(client, subscription_event(event, subscription.razorpay_subscription_id))

    assert reload(subscription).status == status


def test_cancellation_during_the_paid_period_is_cancelled(client, workspace):
    subscription = make_active(workspace)
    subscription.cancel_at_period_end = True
    subscription.save()
    payload = subscription_event(
        "subscription.cancelled",
        subscription.razorpay_subscription_id,
        status="cancelled",
        current_end=ts(subscription.current_period_end),
    )

    post_webhook(client, payload)

    subscription = reload(subscription)
    assert (subscription.status, subscription.cancel_at_period_end) == ("cancelled", False)


@pytest.mark.parametrize("event", ["subscription.cancelled", "subscription.completed"])
def test_ending_after_the_period_is_expired(client, workspace, event):
    subscription = make_active(workspace)
    subscription.current_period_end = timezone.now() - timedelta(minutes=1)
    subscription.save()
    payload = subscription_event(
        event,
        subscription.razorpay_subscription_id,
        status=event.split(".")[1],
        current_end=ts(subscription.current_period_end),
    )

    post_webhook(client, payload)

    assert reload(subscription).status == "expired"


def test_a_cancelled_checkout_returns_to_the_trial(client, checkout):
    post_webhook(
        client, subscription_event("subscription.cancelled", CHECKOUT_ID, status="cancelled")
    )

    subscription = reload(checkout)
    assert (subscription.status, subscription.razorpay_subscription_id) == ("trialing", None)


def test_late_events_do_not_revive_an_ended_subscription(client, workspace):
    subscription = make_active(workspace)
    razorpay_id = subscription.razorpay_subscription_id
    end = ts(subscription.current_period_end)

    post_webhook(
        client,
        subscription_event("subscription.cancelled", razorpay_id, current_end=end),
        event_id="e1",
    )
    post_webhook(client, subscription_event("subscription.activated", razorpay_id), event_id="e2")
    post_webhook(client, subscription_event("subscription.halted", razorpay_id), event_id="e3")

    assert reload(subscription).status == "cancelled"


def test_payment_failed_is_logged_and_keeps_the_status(client, workspace, caplog):
    subscription = make_active(workspace)
    payload = {
        "entity": "event",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {"id": "pay_fail1", "status": "failed", "error_code": "BAD_REQUEST_ERROR"}
            }
        },
    }

    response = post_webhook(client, payload)

    assert response.json() == {"status": "logged"}
    assert reload(subscription).status == "active"
    assert "pay_fail1" in caplog.text
