"""Cashfree Payment Gateway (PG) Payment Links on the seller's own account (App ID + secret key).

Checked against the official docs (September 2026):

- Base URLs: sandbox ``https://sandbox.cashfree.com/pg`` (our ``test`` mode) and production
  ``https://api.cashfree.com/pg`` (``live``). Headers ``x-client-id``, ``x-client-secret`` and
  ``x-api-version`` (the docs show ``2026-01-01``; pinned in :data:`API_VERSION`).
- Create: ``POST /links`` — https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/create
  ``link_id`` (<= 50, alphanumeric, ``-`` and ``_``), ``link_amount`` (rupees, up to 2
  decimals), ``link_currency``, ``link_purpose`` (<= 500), ``customer_details`` (required
  ``customer_phone``; ``customer_name``), ``link_expiry_time`` (ISO 8601),
  ``link_partial_payments``, ``link_notify.send_sms``/``send_email``, ``link_auto_reminders``,
  ``link_meta.return_url`` (<= 250), ``link_notes`` (<= 5 pairs). Response has ``cf_link_id``,
  ``link_id``, ``link_status``, ``link_amount``, ``link_amount_paid``, ``link_url``.
- Fetch: ``GET /links/{link_id}`` — https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/get
  Unknown link → 404 ``invalid_request_error``; bad credentials → 401 ``authentication_error``.
- Cancel: ``POST /links/{link_id}/cancel`` (only ``ACTIVE`` links) —
  https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/cancel
- Paid amount is ``link_amount_paid``. The payment id is not on the link: ``GET
  /links/{link_id}/orders?status=PAID`` (https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/get-orders-for-a-payment-link)
  then ``GET /orders/{order_id}/payments`` → ``cf_payment_id`` with ``payment_status ==
  "SUCCESS"`` (https://www.cashfree.com/docs/api-reference/payments/latest/payments/get-payments-for-order).
- Link statuses: ``ACTIVE``, ``PAID``, ``PARTIALLY_PAID``, ``EXPIRED``, ``CANCELLED`` (the
  webhook docs); the create page also lists ``COMPLETED``, which is treated as paid.
- Webhook (https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/webhooks,
  https://www.cashfree.com/docs/payments/online/webhooks/signature-verification):
  ``{"type": "PAYMENT_LINK_EVENT", "event_time", "data": {link_id, link_status,
  link_amount, link_amount_paid, link_currency, ..., "order": {order_id, transaction_id,
  transaction_status}}}``; ``x-webhook-signature`` = base64(HMAC-SHA256(secret key,
  ``x-webhook-timestamp`` + raw body)). No event id is documented, so events are deduped on a
  sha256 of the body (or an ``x-idempotency-key`` header when present).
- Verify: no dedicated endpoint, so ``GET /links/<unknown id>``: 404 means the keys work.

Never log the secret key or the ``x-client-secret`` header.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from django.conf import settings

from ..exceptions import PaymentAccountInvalid, PaymentAccountMissing, PaymentProviderError
from .base import (
    CANCELLED,
    CREATED,
    EXPIRED,
    PAID,
    PARTIALLY_PAID,
    InvalidWebhookSignature,
    LinkRequest,
    LinkState,
    WebhookLinkUpdate,
    body_digest,
    clean_raw,
    lower_headers,
    paise_to_rupees,
    rupees_to_paise,
)

logger = logging.getLogger(__name__)

PROVIDER = "cashfree"
API_VERSION = "2026-01-01"
BASE_URLS = {
    "test": "https://sandbox.cashfree.com/pg",
    "live": "https://api.cashfree.com/pg",
}
DEFAULT_TIMEOUT = 20.0
IST = ZoneInfo("Asia/Kolkata")
VERIFY_LINK_ID = "upc-credential-check"
STATUSES = {
    "ACTIVE": CREATED,
    "PAID": PAID,
    "COMPLETED": PAID,
    "PARTIALLY_PAID": PARTIALLY_PAID,
    "EXPIRED": EXPIRED,
    "CANCELLED": CANCELLED,
}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def _checked_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise PaymentProviderError(f"Invalid Cashfree {label}.", provider=PROVIDER)
    return value


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)


def cashfree_phone(phone_e164: str) -> str:
    """Cashfree's ``customer_phone``: 10 digits for Indian numbers, digits otherwise."""
    digits = re.sub(r"\D", "", phone_e164 or "")
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    return digits


class CashfreeTransport:
    """Small httpx client with Cashfree auth headers and error mapping."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        mode: str,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise PaymentAccountMissing()
        if mode not in BASE_URLS:
            raise PaymentAccountMissing("Choose test or live mode for your Cashfree account.")
        self._client = httpx.Client(
            base_url=BASE_URLS[mode],
            timeout=getattr(settings, "CASHFREE_TIMEOUT", DEFAULT_TIMEOUT)
            if timeout is None
            else timeout,
            transport=transport,
            headers={
                "x-client-id": client_id,
                "x-client-secret": client_secret,
                "x-api-version": API_VERSION,
                "Accept": "application/json",
            },
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise PaymentProviderError(
                f"Cashfree request failed ({type(exc).__name__}).",
                provider=PROVIDER,
                retryable=True,
            ) from None
        try:
            data = response.json()
        except ValueError:
            data = None
        status = response.status_code
        if response.is_error:
            message = data.get("message") if isinstance(data, dict) else None
            raise PaymentProviderError(
                str(message or f"Cashfree returned HTTP {status}.")[:300],
                provider=PROVIDER,
                status_code=status,
                retryable=status == 429 or status >= 500,
            )
        if data is None:
            raise PaymentProviderError(
                "Cashfree returned an unexpected response.",
                provider=PROVIDER,
                status_code=status,
                retryable=True,
            )
        return data

    def close(self) -> None:
        self._client.close()


class CashfreeProvider:
    name = PROVIDER

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        mode: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._mode = mode
        self._transport = transport

    def __repr__(self) -> str:  # never show secrets
        return f"CashfreeProvider(client_id={self._client_id!r}, mode={self._mode!r})"

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        client = CashfreeTransport(
            client_id=self._client_id,
            client_secret=self._client_secret,
            mode=self._mode,
            transport=self._transport,
        )
        try:
            return client.request(method, path, **kwargs)
        finally:
            client.close()

    def _link_path(self, link_id: str) -> str:
        return f"/links/{_checked_id(link_id, 'link id')}"

    # --- PaymentProvider ---------------------------------------------------------------------

    def verify_credentials(self) -> None:
        try:
            self._call("GET", f"/links/{VERIFY_LINK_ID}")
        except PaymentProviderError as exc:
            if exc.status_code == 404:
                return
            if exc.status_code in (401, 403):
                raise PaymentAccountInvalid() from None
            raise

    def create_link(self, request: LinkRequest) -> LinkState:
        notes = {str(k): str(v) for k, v in list(request.notes.items())[:5]}
        body = {
            "link_id": _checked_id(request.reference_id, "link id"),
            # JSON number with at most 2 decimals; the Decimal is exact before the conversion.
            "link_amount": float(paise_to_rupees(request.amount_paise)),
            "link_currency": request.currency,
            "link_purpose": request.description[:500],
            "customer_details": {
                "customer_phone": cashfree_phone(request.customer_phone_e164),
                "customer_name": request.customer_name,
            },
            "link_expiry_time": request.expire_by.astimezone(IST).isoformat(timespec="seconds"),
            "link_partial_payments": False,
            "link_notify": {"send_sms": False, "send_email": False},
            "link_auto_reminders": False,
            "link_meta": {"return_url": request.return_url[:250]},
            "link_notes": notes,
        }
        try:
            return self._state(self._call("POST", "/links", json=body))
        except PaymentProviderError as exc:
            duplicate = exc.status_code == 409 or (
                exc.status_code == 400 and "exist" in str(exc).lower()
            )
            if duplicate:
                return self.fetch_link(request.reference_id)
            raise

    def fetch_link(self, provider_link_id: str) -> LinkState:
        state = self._state(self._call("GET", self._link_path(provider_link_id)))
        if state.status == PAID and not state.provider_payment_id:
            try:
                payment_id, paid_at = self._successful_payment(provider_link_id)
            except PaymentProviderError as exc:
                logger.warning(
                    "Could not read the Cashfree payment id for link %s: %s",
                    provider_link_id,
                    exc,
                )
            else:
                state = replace(
                    state, provider_payment_id=payment_id, paid_at=paid_at or state.paid_at
                )
        return state

    def _successful_payment(self, link_id: str) -> tuple[str, datetime | None]:
        orders = self._call("GET", f"{self._link_path(link_id)}/orders", params={"status": "PAID"})
        for order in orders if isinstance(orders, list) else []:
            if not isinstance(order, dict) or not order.get("order_id"):
                continue
            order_id = _checked_id(str(order["order_id"]), "order id")
            payments = self._call("GET", f"/orders/{order_id}/payments")
            for payment in payments if isinstance(payments, list) else []:
                if isinstance(payment, dict) and payment.get("payment_status") == "SUCCESS":
                    return (
                        str(payment.get("cf_payment_id") or ""),
                        _parse_time(payment.get("payment_completion_time"))
                        or _parse_time(payment.get("payment_time")),
                    )
        return "", None

    def cancel_link(self, provider_link_id: str) -> LinkState:
        path = f"{self._link_path(provider_link_id)}/cancel"
        try:
            state = self._state(self._call("POST", path))
        except PaymentProviderError as exc:
            if exc.status_code in (400, 409, 422):  # not ACTIVE any more
                return self.fetch_link(provider_link_id)
            raise
        # The cancel succeeded; the documented sample response still shows ACTIVE.
        return replace(state, status=CANCELLED) if state.status == CREATED else state

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> list[WebhookLinkUpdate]:
        lowered = lower_headers(headers)
        timestamp = lowered.get("x-webhook-timestamp", "")
        signature = lowered.get("x-webhook-signature", "").strip()
        if not timestamp or not signature or not self._client_secret:
            raise InvalidWebhookSignature()
        digest = hmac.new(
            self._client_secret.encode(), timestamp.encode() + body, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(base64.b64encode(digest), signature.encode()):
            raise InvalidWebhookSignature()
        try:
            data = json.loads(body)
        except ValueError:
            logger.warning("Cashfree webhook body is not JSON; polling will confirm the link")
            return []
        if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            return []
        event_type = str(data.get("type") or "")
        link = data["data"]
        if event_type != "PAYMENT_LINK_EVENT" or not link.get("link_id"):
            return []
        state = self._state(link)
        order = link.get("order") if isinstance(link.get("order"), dict) else {}
        if state.status == PAID and order.get("transaction_status") == "SUCCESS":
            state = replace(
                state,
                provider_payment_id=str(order.get("transaction_id") or ""),
                paid_at=_parse_time(data.get("event_time")),
            )
        event_id = lowered.get("x-idempotency-key") or body_digest(body)
        return [
            WebhookLinkUpdate(
                event_id=event_id[:100],
                event_type=event_type,
                provider_link_id=state.provider_link_id,
                state=state,
            )
        ]

    def _state(self, data: object) -> LinkState:
        if not isinstance(data, dict):
            raise PaymentProviderError(
                "Cashfree returned an unexpected link.", provider=PROVIDER, retryable=True
            )
        raw_status = str(data.get("link_status") or "")
        status = STATUSES.get(raw_status)
        if status is None:
            logger.warning("Unknown Cashfree link status %r", raw_status)
            status = CREATED
        return LinkState(
            provider_link_id=str(data.get("link_id") or ""),
            short_url=str(data.get("link_url") or ""),
            status=status,
            amount_paid_paise=rupees_to_paise(data.get("link_amount_paid")) or 0,
            raw=clean_raw(data),
            amount_paise=rupees_to_paise(data.get("link_amount")),
            currency=str(data.get("link_currency") or ""),
            expires_at=_parse_time(data.get("link_expiry_time")),
        )
