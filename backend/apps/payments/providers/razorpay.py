"""Razorpay Payment Links on the seller's own account (their key id and key secret).

Checked against the official docs (September 2026):

- Create: ``POST /v1/payment_links`` — https://razorpay.com/docs/api/payments/payment-links/create-standard/
  ``amount`` in paise (>= 100), ``currency``, ``accept_partial``, ``expire_by`` (Unix seconds,
  at least 15 minutes ahead, at most 6 months), ``reference_id`` (<= 40, unique per link),
  ``description`` (<= 2048), ``customer.name``/``customer.contact`` (8-14 characters with the
  country code), ``notify.sms``/``notify.email``, ``reminder_enable``, ``notes`` (<= 15 pairs,
  256 characters per value), ``callback_url`` with ``callback_method="get"``.
- Fetch: ``GET /v1/payment_links/{id}`` — https://razorpay.com/docs/api/payments/payment-links/fetch-id-standard/
  ``status`` is ``created``, ``partially_paid``, ``paid``, ``expired`` or ``cancelled``;
  ``amount_paid`` in paise; ``payments[]`` items have ``payment_id``, ``amount``, ``status``
  (``captured``), ``method`` and ``created_at``.
- Fetch all (idempotent create fallback): ``GET /v1/payment_links?reference_id=``
  — https://razorpay.com/docs/api/payments/payment-links/fetch-all-standard/
- Cancel: ``POST /v1/payment_links/{id}/cancel`` — https://razorpay.com/docs/api/payments/payment-links/cancel-standard/
  Paid, partially paid, expired and cancelled links can't be cancelled.
- Callback: Razorpay appends ``razorpay_payment_id``, ``razorpay_payment_link_id``,
  ``razorpay_payment_link_reference_id``, ``razorpay_payment_link_status`` and
  ``razorpay_signature``: hex HMAC-SHA256 with the key secret of
  ``"{link_id}|{reference_id}|{status}|{payment_id}"`` (razorpay-python
  ``utility.verify_payment_link_signature``) — https://razorpay.com/docs/payments/payment-links/apis/
- Webhooks: ``payment_link.paid``, ``payment_link.partially_paid``, ``payment_link.expired``,
  ``payment_link.cancelled`` (https://razorpay.com/docs/webhooks/payment-links/); the
  ``X-Razorpay-Signature`` header is the hex HMAC-SHA256 of the raw body with the webhook
  secret, and ``x-razorpay-event-id`` is unique per event
  (https://razorpay.com/docs/webhooks/validate-test/).
- Verify: ``GET /v1/payments?count=1`` (``count`` is documented, 1-100) —
  https://razorpay.com/docs/api/payments/fetch-all-payments/ ; bad keys answer 401.

Never log the key secret, the webhook secret or signatures.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from django.utils import timezone

from common.razorpay import (
    RazorpayError,
    RazorpayNotConfigured,
    RazorpayTransport,
    checked_id,
    hmac_sha256_hex,
    signature_matches,
    webhook_signature_is_valid,
)

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
)

logger = logging.getLogger(__name__)

PROVIDER = "razorpay"
MIN_EXPIRY = timedelta(minutes=15)
EXPIRY_MARGIN = timedelta(minutes=1)
STATUSES = {
    "created": CREATED,
    "paid": PAID,
    "partially_paid": PARTIALLY_PAID,
    "expired": EXPIRED,
    "cancelled": CANCELLED,
}
EVENT_STATUSES = {
    "payment_link.paid": PAID,
    "payment_link.partially_paid": PARTIALLY_PAID,
    "payment_link.expired": EXPIRED,
    "payment_link.cancelled": CANCELLED,
}
CALLBACK_PARAMS = (
    "razorpay_payment_link_id",
    "razorpay_payment_link_reference_id",
    "razorpay_payment_link_status",
    "razorpay_payment_id",
)


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _wrap(exc: RazorpayError) -> PaymentProviderError:
    return PaymentProviderError(
        str(exc), provider=PROVIDER, status_code=exc.status_code, retryable=exc.retryable
    )


class RazorpayProvider:
    name = PROVIDER

    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        webhook_secret: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret
        self._transport = transport

    def __repr__(self) -> str:  # never show secrets
        return f"RazorpayProvider(key_id={self._key_id!r})"

    # --- HTTP --------------------------------------------------------------------------------

    def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            client = RazorpayTransport(
                key_id=self._key_id, key_secret=self._key_secret, transport=self._transport
            )
        except RazorpayNotConfigured:
            raise PaymentAccountMissing() from None
        try:
            return client.request(method, path, **kwargs)
        except RazorpayError as exc:
            raise _wrap(exc) from None
        finally:
            client.close()

    @staticmethod
    def _link_path(provider_link_id: str) -> str:
        try:
            return f"/payment_links/{checked_id(provider_link_id, label='payment link id')}"
        except RazorpayError as exc:
            raise _wrap(exc) from None

    # --- PaymentProvider ---------------------------------------------------------------------

    def verify_credentials(self) -> None:
        try:
            self._call("GET", "/payments", params={"count": 1})
        except PaymentProviderError as exc:
            if exc.status_code in (401, 403):
                raise PaymentAccountInvalid() from None
            raise

    def create_link(self, request: LinkRequest) -> LinkState:
        earliest = timezone.now() + MIN_EXPIRY + EXPIRY_MARGIN
        expire_by = max(request.expire_by, earliest)
        body = {
            "amount": int(request.amount_paise),
            "currency": request.currency,
            "accept_partial": False,
            "expire_by": int(expire_by.timestamp()),
            "reference_id": request.reference_id,
            "description": request.description[:2048],
            "customer": {"name": request.customer_name, "contact": request.customer_phone_e164},
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {str(k): str(v)[:256] for k, v in list(request.notes.items())[:15]},
            "callback_url": request.return_url,
            "callback_method": "get",
        }
        try:
            return self._state(self._call("POST", "/payment_links", json=body))
        except PaymentProviderError as exc:
            if exc.status_code == 400 and "reference" in str(exc).lower():
                existing = self._find_by_reference(request.reference_id)
                if existing is not None:
                    return existing
            raise

    def _find_by_reference(self, reference_id: str) -> LinkState | None:
        data = self._call("GET", "/payment_links", params={"reference_id": reference_id})
        for item in data.get("payment_links") or []:
            if isinstance(item, dict) and item.get("reference_id") == reference_id:
                return self._state(item)
        return None

    def fetch_link(self, provider_link_id: str) -> LinkState:
        return self._state(self._call("GET", self._link_path(provider_link_id)))

    def cancel_link(self, provider_link_id: str) -> LinkState:
        path = f"{self._link_path(provider_link_id)}/cancel"
        try:
            state = self._state(self._call("POST", path))
        except PaymentProviderError as exc:
            if exc.status_code == 400:  # already paid, expired or cancelled
                return self.fetch_link(provider_link_id)
            raise
        return replace(state, status=CANCELLED) if state.status == CREATED else state

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> list[WebhookLinkUpdate]:
        lowered = lower_headers(headers)
        if not webhook_signature_is_valid(
            body, lowered.get("x-razorpay-signature"), self._webhook_secret
        ):
            raise InvalidWebhookSignature()
        try:
            data = json.loads(body)
        except ValueError:
            logger.warning("Razorpay webhook body is not JSON")
            return []
        if not isinstance(data, dict):
            return []
        event = str(data.get("event") or "")
        if event not in EVENT_STATUSES:
            return []
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        entity = (payload.get("payment_link") or {}).get("entity")
        if not isinstance(entity, dict) or not entity.get("id"):
            return []
        payment = (payload.get("payment") or {}).get("entity")
        payment = payment if isinstance(payment, dict) else {}
        state = self._state(entity)
        if state.status == CREATED:  # entity without a status: trust the signed event name
            state = replace(state, status=EVENT_STATUSES[event])
        if payment.get("id"):
            state = replace(
                state,
                provider_payment_id=str(payment["id"]),
                paid_at=state.paid_at or _timestamp(payment.get("created_at")),
            )
        event_id = lowered.get("x-razorpay-event-id") or body_digest(body)
        return [
            WebhookLinkUpdate(
                event_id=event_id[:100],
                event_type=event,
                provider_link_id=state.provider_link_id,
                state=state,
            )
        ]

    # --- Extras ------------------------------------------------------------------------------

    def callback_signature_is_valid(self, params: Mapping[str, str]) -> bool:
        """Check the ``razorpay_signature`` Razorpay appends to the callback URL.

        Informational only: the return page always re-fetches the link.
        """
        values = [params.get(name) for name in CALLBACK_PARAMS]
        signature = params.get("razorpay_signature")
        if not self._key_secret or not signature or any(v is None for v in values):
            return False
        message = "|".join(str(v) for v in values).encode()
        return signature_matches(hmac_sha256_hex(self._key_secret, message), signature)

    def _state(self, data: Mapping[str, Any]) -> LinkState:
        raw_status = str(data.get("status") or "")
        status = STATUSES.get(raw_status)
        if status is None:
            logger.warning("Unknown Razorpay payment link status %r", raw_status)
            status = CREATED
        payments = [p for p in (data.get("payments") or []) if isinstance(p, dict)]
        captured = [p for p in payments if p.get("status") == "captured"]
        payment = captured[-1] if captured else None
        paid_at = None
        payment_id = ""
        if payment is not None:
            payment_id = str(payment.get("payment_id") or payment.get("id") or "")
            paid_at = _timestamp(payment.get("created_at"))
        if status == PAID and paid_at is None:
            paid_at = _timestamp(data.get("updated_at"))
        return LinkState(
            provider_link_id=str(data.get("id") or ""),
            short_url=str(data.get("short_url") or ""),
            status=status,
            amount_paid_paise=_int(data.get("amount_paid")) or 0,
            provider_payment_id=payment_id,
            paid_at=paid_at,
            raw=clean_raw(data),
            amount_paise=_int(data.get("amount")),
            currency=str(data.get("currency") or ""),
            expires_at=_timestamp(data.get("expire_by")),
        )
