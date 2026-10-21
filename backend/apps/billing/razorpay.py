"""Razorpay API access (auto-pay subscriptions and one-time orders) and signature checks.

Always go through :func:`get_razorpay_client`; tests install :class:`FakeRazorpayClient` with
:func:`override_razorpay_client` and never reach the network. Never log key secrets, webhook
secrets or signatures.

The HTTP transport, errors and webhook signature check live in :mod:`common.razorpay` (shared with
``apps.payments``); the names are re-exported here for existing imports.

Razorpay plans (``RAZORPAY_PLAN_IDS``) must be created with GST-inclusive amounts: Razorpay charges
the plan amount as is, while UpChatz prices exclude GST and invoices add it on top.
"""

import itertools
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Protocol

from django.conf import settings

from common.razorpay import (
    API_BASE_URL,
    JSON,
    RazorpayError,
    RazorpayNotConfigured,
    RazorpayTransport,
    checked_id,
    hmac_sha256_hex,
    signature_matches,
    webhook_signature_is_valid,
)

__all__ = (
    "API_BASE_URL",
    "JSON",
    "TOTAL_COUNT",
    "FakeRazorpayClient",
    "HttpRazorpayClient",
    "RazorpayClient",
    "RazorpayError",
    "RazorpayNotConfigured",
    "checkout_signature_is_valid",
    "get_razorpay_client",
    "order_signature_is_valid",
    "override_razorpay_client",
    "plan_for_razorpay_plan_id",
    "plan_id_for",
    "webhook_signature_is_valid",
)

# Billing cycles before a Razorpay subscription completes (10 years either way).
TOTAL_COUNT = {"monthly": 120, "annual": 10}


class RazorpayClient(Protocol):
    def create_subscription(
        self, *, plan_id: str, total_count: int, notes: Mapping[str, str]
    ) -> JSON: ...

    def fetch_subscription(self, subscription_id: str) -> JSON: ...

    def cancel_subscription(self, subscription_id: str, *, at_cycle_end: bool) -> JSON: ...

    def create_order(
        self, *, amount: int, currency: str, receipt: str, notes: Mapping[str, str]
    ) -> JSON: ...

    def fetch_order(self, order_id: str) -> JSON: ...

    def fetch_order_payments(self, order_id: str) -> list[JSON]: ...


def _checked_id(subscription_id: str) -> str:
    return checked_id(subscription_id, label="Razorpay subscription id")


def _checked_order_id(order_id: str) -> str:
    return checked_id(order_id, label="Razorpay order id")


class HttpRazorpayClient(RazorpayTransport):
    """Subscriptions and orders over the shared Razorpay transport (basic auth with the platform
    keys)."""

    def create_subscription(
        self, *, plan_id: str, total_count: int, notes: Mapping[str, str]
    ) -> JSON:
        body = {
            "plan_id": plan_id,
            "total_count": total_count,
            "quantity": 1,
            "customer_notify": 1,
            "notes": dict(notes),
        }
        return self.request("POST", "/subscriptions", json=body)

    def fetch_subscription(self, subscription_id: str) -> JSON:
        return self.request("GET", f"/subscriptions/{_checked_id(subscription_id)}")

    def cancel_subscription(self, subscription_id: str, *, at_cycle_end: bool) -> JSON:
        return self.request(
            "POST",
            f"/subscriptions/{_checked_id(subscription_id)}/cancel",
            json={"cancel_at_cycle_end": 1 if at_cycle_end else 0},
        )

    def create_order(
        self, *, amount: int, currency: str, receipt: str, notes: Mapping[str, str]
    ) -> JSON:
        """``POST /v1/orders``: one payment of ``amount`` paise (a prepaid plan period)."""
        body = {"amount": amount, "currency": currency, "receipt": receipt, "notes": dict(notes)}
        return self.request("POST", "/orders", json=body)

    def fetch_order(self, order_id: str) -> JSON:
        return self.request("GET", f"/orders/{_checked_order_id(order_id)}")

    def fetch_order_payments(self, order_id: str) -> list[JSON]:
        """The order's payment attempts (``items`` of the collection), oldest first."""
        data = self.request("GET", f"/orders/{_checked_order_id(order_id)}/payments")
        items = data.get("items")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _request(self, method: str, path: str, *, json: JSON | None = None) -> JSON:
        """Kept for callers of the wave-2 private name."""
        return self.request(method, path, json=json)


class FakeRazorpayClient:
    """In-memory Razorpay for tests. ``calls`` records every call; set ``fail_with`` to raise."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, JSON] = {}
        self.orders: dict[str, JSON] = {}
        self.payments: dict[str, list[JSON]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_with: RazorpayError | None = None
        self._ids = itertools.count(1)

    def create_subscription(
        self, *, plan_id: str, total_count: int, notes: Mapping[str, str]
    ) -> JSON:
        self._record("create_subscription", plan_id=plan_id, total_count=total_count, notes=notes)
        subscription_id = f"sub_fake{next(self._ids):06d}"
        entity = {
            "id": subscription_id,
            "entity": "subscription",
            "plan_id": plan_id,
            "status": "created",
            "total_count": total_count,
            "paid_count": 0,
            "notes": dict(notes),
            "short_url": f"https://rzp.io/i/{subscription_id}",
        }
        self.subscriptions[subscription_id] = entity
        return dict(entity)

    def fetch_subscription(self, subscription_id: str) -> JSON:
        self._record("fetch_subscription", subscription_id=subscription_id)
        return dict(self._get(subscription_id))

    def cancel_subscription(self, subscription_id: str, *, at_cycle_end: bool) -> JSON:
        self._record(
            "cancel_subscription", subscription_id=subscription_id, at_cycle_end=at_cycle_end
        )
        entity = self._get(subscription_id)
        if not at_cycle_end:
            entity["status"] = "cancelled"
        return dict(entity)

    def create_order(
        self, *, amount: int, currency: str, receipt: str, notes: Mapping[str, str]
    ) -> JSON:
        self._record("create_order", amount=amount, currency=currency, receipt=receipt, notes=notes)
        order_id = f"order_fake{next(self._ids):06d}"
        entity = {
            "id": order_id,
            "entity": "order",
            "amount": amount,
            "amount_paid": 0,
            "amount_due": amount,
            "currency": currency,
            "receipt": receipt,
            "status": "created",
            "attempts": 0,
            "notes": dict(notes),
        }
        self.orders[order_id] = entity
        return dict(entity)

    def fetch_order(self, order_id: str) -> JSON:
        self._record("fetch_order", order_id=order_id)
        return dict(self._get_order(order_id))

    def fetch_order_payments(self, order_id: str) -> list[JSON]:
        self._record("fetch_order_payments", order_id=order_id)
        self._get_order(order_id)
        return [dict(payment) for payment in self.payments.get(order_id, [])]

    def pay_order(self, order_id: str, *, payment_id: str = "pay_fake000001") -> JSON:
        """Mark an order paid with a captured payment, as Razorpay does after Checkout."""
        order = self._get_order(order_id)
        order.update(status="paid", amount_paid=order["amount"], amount_due=0)
        order["attempts"] += 1
        payment = {
            "id": payment_id,
            "entity": "payment",
            "amount": order["amount"],
            "currency": order["currency"],
            "status": "captured",
            "order_id": order_id,
            "captured": True,
        }
        self.payments.setdefault(order_id, []).append(payment)
        return dict(payment)

    def fail_order_payment(self, order_id: str, *, payment_id: str = "pay_failed01") -> JSON:
        """Record a failed attempt; the order stays ``attempted``."""
        order = self._get_order(order_id)
        order["status"] = "attempted"
        order["attempts"] += 1
        payment = {
            "id": payment_id,
            "entity": "payment",
            "amount": order["amount"],
            "status": "failed",
            "order_id": order_id,
        }
        self.payments.setdefault(order_id, []).append(payment)
        return dict(payment)

    def calls_to(self, name: str) -> list[dict]:
        return [kwargs for call, kwargs in self.calls if call == name]

    def _get_order(self, order_id: str) -> JSON:
        entity = self.orders.get(order_id)
        if entity is None:
            raise RazorpayError(
                "The id provided does not exist", status_code=400, code="BAD_REQUEST_ERROR"
            )
        return entity

    def _get(self, subscription_id: str) -> JSON:
        entity = self.subscriptions.get(subscription_id)
        if entity is None:
            raise RazorpayError(
                "The id provided does not exist", status_code=400, code="BAD_REQUEST_ERROR"
            )
        return entity

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))
        if self.fail_with is not None:
            raise self.fail_with


_override: RazorpayClient | None = None


def get_razorpay_client() -> RazorpayClient:
    if _override is not None:
        return _override
    return HttpRazorpayClient(
        key_id=settings.RAZORPAY_KEY_ID, key_secret=settings.RAZORPAY_KEY_SECRET
    )


@contextmanager
def override_razorpay_client(client: RazorpayClient) -> Iterator[RazorpayClient]:
    global _override
    previous = _override
    _override = client
    try:
        yield client
    finally:
        _override = previous


# --- Plans ----------------------------------------------------------------------------------


def plan_id_for(plan_slug: str, interval: str) -> str:
    """Razorpay plan id for a plan and interval, from ``RAZORPAY_PLAN_IDS``."""
    plan_id = (settings.RAZORPAY_PLAN_IDS or {}).get(plan_slug, {}).get(interval)
    if not plan_id:
        raise RazorpayNotConfigured(f"No Razorpay plan id configured for {plan_slug}/{interval}.")
    return plan_id


def plan_for_razorpay_plan_id(razorpay_plan_id: object) -> tuple[str, str] | None:
    """``(plan slug, interval)`` for a Razorpay plan id, or None when it isn't configured."""
    if not isinstance(razorpay_plan_id, str) or not razorpay_plan_id:
        return None
    for slug, intervals in (settings.RAZORPAY_PLAN_IDS or {}).items():
        for interval, plan_id in (intervals or {}).items():
            if plan_id == razorpay_plan_id:
                return slug, interval
    return None


# --- Signatures -----------------------------------------------------------------------------


def checkout_signature_is_valid(
    *, payment_id: str, subscription_id: str, signature: str, secret: str
) -> bool:
    """Checkout (subscription mode) signs ``razorpay_payment_id|razorpay_subscription_id``."""
    if not (secret and payment_id and subscription_id):
        return False
    expected = hmac_sha256_hex(secret, f"{payment_id}|{subscription_id}".encode())
    return signature_matches(expected, signature)


def order_signature_is_valid(
    *, payment_id: str, order_id: str, signature: str, secret: str
) -> bool:
    """Checkout (order mode) signs ``razorpay_order_id|razorpay_payment_id``."""
    if not (secret and payment_id and order_id):
        return False
    expected = hmac_sha256_hex(secret, f"{order_id}|{payment_id}".encode())
    return signature_matches(expected, signature)
