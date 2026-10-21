"""Shared test data and helpers for billing tests."""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.billing import prices, services
from apps.billing.models import Plan, RazorpayPlan
from apps.billing.razorpay import FakeRazorpayClient, RazorpayError

# Seller in test settings is in Karnataka (29): Maharashtra buyers pay IGST, Karnataka CGST+SGST.
MAHARASHTRA_PROFILE = {
    "legal_name": "Asha Traders Private Limited",
    "gstin": "27AAPFU0939F1ZV",
    "email": "accounts@asha.example",
    "address_line1": "12 Linking Road",
    "address_line2": "",
    "city": "Mumbai",
    "state_code": "27",
    "postal_code": "400050",
}
KARNATAKA_PROFILE = {
    "legal_name": "Bengaluru Blooms LLP",
    "gstin": "29AAGCB7383J1Z4",
    "email": "billing@blooms.example",
    "address_line1": "88 MG Road",
    "address_line2": "",
    "city": "Bengaluru",
    "state_code": "29",
    "postal_code": "560001",
}


def seed_razorpay_plans() -> None:
    """Save the ``RazorpayPlan`` copies of the test plan ids (``plan_test_<slug>_<interval>``) as
    if they had been fetched, so tests not about pricing make no ``fetch_plan`` call."""
    fake = FakeRazorpayClient()
    for plan in Plan.objects.all():
        for interval in ("monthly", "annual"):
            plan_id = plan.razorpay_plan_id(interval)
            if not plan_id or RazorpayPlan.objects.filter(pk=plan_id).exists():
                continue
            try:
                entity = fake.fetch_plan(plan_id)
            except RazorpayError:
                continue
            prices.store_snapshot(
                plan_id, prices.parse_plan_entity(plan_id, entity), plan=plan, interval=interval
            )


def ts(moment: datetime) -> int:
    return int(moment.timestamp())


def checkout_signature(payment_id: str, subscription_id: str, secret: str | None = None) -> str:
    key = (secret or settings.RAZORPAY_KEY_SECRET).encode()
    return hmac.new(key, f"{payment_id}|{subscription_id}".encode(), hashlib.sha256).hexdigest()


def order_signature(payment_id: str, order_id: str, secret: str | None = None) -> str:
    """Razorpay Checkout's signature for a one-time order: ``order_id|payment_id``."""
    key = (secret or settings.RAZORPAY_KEY_SECRET).encode()
    return hmac.new(key, f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def order_paid_event(
    order_id: str, amount: int, *, payment_id: str = "pay_order0001", created_at: int | None = None
) -> dict:
    """A Razorpay ``order.paid`` webhook body."""
    return {
        "entity": "event",
        "account_id": "acc_test",
        "event": "order.paid",
        "contains": ["payment", "order"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount,
                    "currency": "INR",
                    "status": "captured",
                    "order_id": order_id,
                    "created_at": created_at,
                }
            },
            "order": {
                "entity": {
                    "id": order_id,
                    "entity": "order",
                    "amount": amount,
                    "amount_paid": amount,
                    "amount_due": 0,
                    "currency": "INR",
                    "status": "paid",
                }
            },
        },
        "created_at": ts(timezone.now()),
    }


def webhook_signature(body: bytes, secret: str | None = None) -> str:
    key = (secret or settings.RAZORPAY_WEBHOOK_SECRET).encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def subscription_event(
    event: str,
    subscription_id: str,
    *,
    plan_id: str = "plan_test_pro_monthly",
    status: str = "active",
    current_start: int | None = None,
    current_end: int | None = None,
    payment: dict | None = None,
) -> dict:
    entity = {
        "id": subscription_id,
        "entity": "subscription",
        "plan_id": plan_id,
        "customer_id": "cust_test1",
        "status": status,
        "current_start": current_start,
        "current_end": current_end,
        "notes": {},
    }
    body = {
        "entity": "event",
        "account_id": "acc_test",
        "event": event,
        "contains": ["subscription"],
        "payload": {"subscription": {"entity": entity}},
        "created_at": ts(timezone.now()),
    }
    if payment is not None:
        body["contains"].append("payment")
        body["payload"]["payment"] = {"entity": payment}
    return body


def post_webhook(client, payload: dict, *, event_id: str | None = "evt_test1", signature=None):
    body = json.dumps(payload).encode()
    headers = {
        "HTTP_X_RAZORPAY_SIGNATURE": webhook_signature(body) if signature is None else signature
    }
    if event_id is not None:
        headers["HTTP_X_RAZORPAY_EVENT_ID"] = event_id
    return client.post("/webhooks/razorpay/", data=body, content_type="application/json", **headers)


def cashfree_signature(body: bytes, timestamp: str, secret: str | None = None) -> str:
    key = (secret or settings.BILLING_CASHFREE_SECRET).encode()
    digest = hmac.new(key, timestamp.encode() + body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def cashfree_payment_event(
    order_id: str,
    order_amount: float,
    *,
    event_type: str = "PAYMENT_SUCCESS_WEBHOOK",
    payment_status: str = "SUCCESS",
    cf_payment_id: int | str = 885000777,
) -> dict:
    """A Cashfree PG payment webhook body (API version 2025-01-01 and later)."""
    return {
        "data": {
            "order": {
                "order_id": order_id,
                "order_amount": order_amount,
                "order_currency": "INR",
                "order_tags": None,
            },
            "payment": {
                "cf_payment_id": cf_payment_id,
                "payment_status": payment_status,
                "payment_amount": order_amount,
                "payment_currency": "INR",
                "payment_message": "Transaction successful",
                "payment_time": "2026-10-10T12:00:05+05:30",
                "payment_group": "upi",
            },
            "customer_details": {"customer_id": "abc", "customer_phone": "9876543210"},
        },
        "event_time": "2026-10-10T12:00:07+05:30",
        "type": event_type,
    }


def post_cashfree_webhook(
    client, payload: dict, *, timestamp: str = "1760078407", signature: str | None = None
):
    body = json.dumps(payload).encode()
    headers = {"HTTP_X_WEBHOOK_TIMESTAMP": timestamp}
    if signature is not False:
        headers["HTTP_X_WEBHOOK_SIGNATURE"] = (
            cashfree_signature(body, timestamp) if signature is None else signature
        )
    return client.post(
        "/webhooks/cashfree/billing/", data=body, content_type="application/json", **headers
    )


def make_cashfree_active(
    workspace, *, plan: str = "growth", interval: str = "monthly", days_left: float = 25
):
    """An active prepaid Cashfree plan with ``days_left`` days of its period remaining."""
    subscription = services.get_subscription(workspace)
    now = timezone.now()
    subscription.status = "active"
    subscription.provider = "cashfree"
    subscription.prepaid = True
    subscription.plan_id = plan
    subscription.interval = interval
    subscription.activated_at = now - timedelta(days=5)
    subscription.current_period_start = now - timedelta(days=5)
    subscription.current_period_end = now + timedelta(days=days_left)
    subscription.save()
    return subscription


def make_razorpay_prepaid_active(
    workspace, *, plan: str = "growth", interval: str = "monthly", days_left: float = 25
):
    """An active prepaid (one-time) Razorpay plan with ``days_left`` days of its period left."""
    subscription = make_cashfree_active(
        workspace, plan=plan, interval=interval, days_left=days_left
    )
    subscription.provider = "razorpay"
    subscription.save()
    return subscription


def make_active(workspace, razorpay_id: str = "sub_active1"):
    """A paid, active Growth subscription 5 days into a 30-day period."""
    subscription = services.get_subscription(workspace)
    now = timezone.now()
    subscription.status = "active"
    subscription.razorpay_subscription_id = razorpay_id
    subscription.activated_at = now - timedelta(days=5)
    subscription.current_period_start = now - timedelta(days=5)
    subscription.current_period_end = now + timedelta(days=25)
    subscription.save()
    return subscription
