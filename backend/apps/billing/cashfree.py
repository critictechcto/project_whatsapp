"""Cashfree Payment Gateway orders for UpChatz's prepaid plans (platform keys from settings).

Always go through :func:`get_cashfree_client`; tests install :class:`FakeCashfreeClient` with
:func:`override_cashfree_client` and never reach the network. Never log the secret key or
webhook signatures. Checked against the official docs (September 2026):

- Create: ``POST /orders`` with ``x-idempotency-key`` —
  https://www.cashfree.com/docs/api-reference/payments/latest/orders/create
  Response has ``cf_order_id``, ``order_id``, ``order_status`` (``ACTIVE``) and
  ``payment_session_id`` for Cashfree Checkout (JS SDK v3).
- Fetch: ``GET /orders/{order_id}`` — ``order_status`` is ``ACTIVE``, ``PAID``, ``EXPIRED``,
  ``TERMINATED`` or ``TERMINATION_REQUESTED``.
- Payments: ``GET /orders/{order_id}/payments`` — a list; the paid one has
  ``payment_status == "SUCCESS"`` and its ``cf_payment_id``.

The transport, errors and the webhook signature check live in :mod:`common.cashfree`.
"""

import itertools
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol

from django.conf import settings

from common.cashfree import (
    JSON,
    CashfreeError,
    CashfreeNotConfigured,
    CashfreeTransport,
    checked_id,
    webhook_signature_is_valid,
)

__all__ = (
    "JSON",
    "CashfreeClient",
    "CashfreeError",
    "CashfreeNotConfigured",
    "FakeCashfreeClient",
    "HttpCashfreeClient",
    "get_cashfree_client",
    "override_cashfree_client",
    "webhook_signature_is_valid",
)


class CashfreeClient(Protocol):
    def create_order(self, body: JSON) -> JSON: ...

    def fetch_order(self, order_id: str) -> JSON: ...

    def fetch_order_payments(self, order_id: str) -> list[JSON]: ...


def _order_path(order_id: str) -> str:
    return f"/orders/{checked_id(order_id, label='Cashfree order id')}"


class HttpCashfreeClient(CashfreeTransport):
    """Orders over the shared Cashfree transport. ``body["order_id"]`` is the idempotency key."""

    def create_order(self, body: JSON) -> JSON:
        order_id = checked_id(body.get("order_id"), label="Cashfree order id")
        data = self.request("POST", "/orders", json=body, headers={"x-idempotency-key": order_id})
        return _object(data)

    def fetch_order(self, order_id: str) -> JSON:
        return _object(self.request("GET", _order_path(order_id)))

    def fetch_order_payments(self, order_id: str) -> list[JSON]:
        data = self.request("GET", f"{_order_path(order_id)}/payments")
        if not isinstance(data, list):
            raise CashfreeError("Cashfree returned unexpected payments.", retryable=True)
        return [item for item in data if isinstance(item, dict)]


def _object(data: Any) -> JSON:
    if not isinstance(data, dict):
        raise CashfreeError("Cashfree returned an unexpected order.", retryable=True)
    return data


class FakeCashfreeClient:
    """In-memory Cashfree for tests. ``calls`` records every call; set ``fail_with`` to raise.

    Orders start ``ACTIVE``; :meth:`pay` marks one ``PAID`` with a SUCCESS payment.
    """

    def __init__(self) -> None:
        self.orders: dict[str, JSON] = {}
        self.payments: dict[str, list[JSON]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_with: CashfreeError | None = None
        self._ids = itertools.count(1)

    def create_order(self, body: JSON) -> JSON:
        self._record("create_order", body=body)
        order_id = body["order_id"]
        if order_id not in self.orders:
            number = next(self._ids)
            self.orders[order_id] = {
                **body,
                "cf_order_id": str(5000000 + number),
                "order_status": "ACTIVE",
                "payment_session_id": f"session_fake{number:06d}",
            }
        return dict(self.orders[order_id])

    def fetch_order(self, order_id: str) -> JSON:
        self._record("fetch_order", order_id=order_id)
        return dict(self._get(order_id))

    def fetch_order_payments(self, order_id: str) -> list[JSON]:
        self._record("fetch_order_payments", order_id=order_id)
        self._get(order_id)
        return [dict(payment) for payment in self.payments.get(order_id, [])]

    def pay(self, order_id: str, *, cf_payment_id: str = "885000001") -> JSON:
        """Mark an order paid, as Cashfree does after a successful payment."""
        order = self._get(order_id)
        order["order_status"] = "PAID"
        payment = {
            "cf_payment_id": cf_payment_id,
            "order_id": order_id,
            "payment_status": "SUCCESS",
            "payment_amount": order.get("order_amount"),
            "payment_currency": "INR",
        }
        self.payments.setdefault(order_id, []).append(payment)
        return payment

    def set_status(self, order_id: str, status: str) -> None:
        self._get(order_id)["order_status"] = status

    def calls_to(self, name: str) -> list[dict]:
        return [kwargs for call, kwargs in self.calls if call == name]

    def _get(self, order_id: str) -> JSON:
        order = self.orders.get(order_id)
        if order is None:
            raise CashfreeError("order not found", status_code=404)
        return order

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))
        if self.fail_with is not None:
            raise self.fail_with


_override: CashfreeClient | None = None


def get_cashfree_client() -> CashfreeClient:
    if _override is not None:
        return _override
    return HttpCashfreeClient(
        client_id=settings.BILLING_CASHFREE_APP_ID,
        client_secret=settings.BILLING_CASHFREE_SECRET,
        mode=settings.CASHFREE_ENV,
    )


@contextmanager
def override_cashfree_client(client: CashfreeClient) -> Iterator[CashfreeClient]:
    global _override
    previous = _override
    _override = client
    try:
        yield client
    finally:
        _override = previous
