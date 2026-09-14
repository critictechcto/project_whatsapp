"""Shared test data and helpers for billing tests."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.billing import services

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


def ts(moment: datetime) -> int:
    return int(moment.timestamp())


def checkout_signature(payment_id: str, subscription_id: str, secret: str | None = None) -> str:
    key = (secret or settings.RAZORPAY_KEY_SECRET).encode()
    return hmac.new(key, f"{payment_id}|{subscription_id}".encode(), hashlib.sha256).hexdigest()


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
