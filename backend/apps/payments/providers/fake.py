"""In-memory payment provider for tests (this app's and other apps').

Usage::

    from apps.payments.testing import fake_payments  # noqa: F401  (pytest fixture)

    def test_something(fake_payments):
        link = services.create_payment_link(...)
        fake_payments.mark_paid(link.provider_link_id)
        services.refresh_payment_link(link)   # emits PaymentLinkPaid on commit

or, without the fixture, ``with override_provider(FakePaymentProvider()) as fake: ...``.
"""

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime

from django.utils import timezone

from ..exceptions import PaymentAccountInvalid, PaymentProviderError
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
    lower_headers,
)

SIGNATURE_HEADER = "x-fake-signature"
VALID_SIGNATURE = "valid"


class FakePaymentProvider:
    name = "fake"

    def __init__(self) -> None:
        self.links: dict[str, LinkState] = {}
        self.requests: dict[str, LinkRequest] = {}
        self.calls: list[tuple[str, str]] = []
        self.credentials_valid = True
        self._errors: dict[str, list[Exception]] = {}
        self._counter = 0

    # --- Test helpers ------------------------------------------------------------------------

    def fail_next(self, method: str, exc: Exception | None = None) -> None:
        """Make the next ``method`` call raise ``exc`` (default: a retryable gateway error)."""
        exc = exc or PaymentProviderError(
            "Gateway unavailable.", provider=self.name, status_code=503, retryable=True
        )
        self._errors.setdefault(method, []).append(exc)

    def calls_to(self, method: str) -> list[str]:
        return [arg for name, arg in self.calls if name == method]

    def set_state(self, provider_link_id: str, **changes) -> LinkState:
        state = replace(self.links[provider_link_id], **changes)
        self.links[provider_link_id] = state
        return state

    def mark_paid(
        self,
        provider_link_id: str,
        *,
        amount_paise: int | None = None,
        currency: str | None = None,
        payment_id: str | None = None,
        paid_at: datetime | None = None,
    ) -> LinkState:
        current = self.links[provider_link_id]
        return self.set_state(
            provider_link_id,
            status=PAID,
            amount_paid_paise=current.amount_paise if amount_paise is None else amount_paise,
            currency=current.currency if currency is None else currency,
            provider_payment_id=payment_id or f"pay_fake_{provider_link_id}",
            paid_at=paid_at or timezone.now(),
        )

    def mark_partially_paid(self, provider_link_id: str, amount_paise: int) -> LinkState:
        return self.set_state(
            provider_link_id, status=PARTIALLY_PAID, amount_paid_paise=amount_paise
        )

    def mark_expired(self, provider_link_id: str) -> LinkState:
        return self.set_state(provider_link_id, status=EXPIRED)

    def mark_cancelled(self, provider_link_id: str) -> LinkState:
        return self.set_state(provider_link_id, status=CANCELLED)

    def webhook(
        self, provider_link_id: str, *, event_id: str, include_state: bool = True
    ) -> tuple[dict[str, str], bytes]:
        """Headers and body of a signed fake webhook for ``provider_link_id``."""
        body = json.dumps(
            {
                "event_id": event_id,
                "event_type": "fake.link_updated",
                "provider_link_id": provider_link_id,
                "include_state": include_state,
            }
        ).encode()
        return {SIGNATURE_HEADER: VALID_SIGNATURE}, body

    # --- PaymentProvider ---------------------------------------------------------------------

    def _record(self, method: str, arg: str = "") -> None:
        self.calls.append((method, arg))
        pending = self._errors.get(method)
        if pending:
            raise pending.pop(0)

    def _get(self, provider_link_id: str) -> LinkState:
        try:
            return self.links[provider_link_id]
        except KeyError:
            raise PaymentProviderError(
                "Link not found.", provider=self.name, status_code=404
            ) from None

    def verify_credentials(self) -> None:
        self._record("verify_credentials")
        if not self.credentials_valid:
            raise PaymentAccountInvalid()

    def create_link(self, request: LinkRequest) -> LinkState:
        self._record("create_link", request.reference_id)
        for link_id, existing in self.requests.items():
            if existing.reference_id == request.reference_id:
                return self.links[link_id]
        self._counter += 1
        link_id = f"plink_fake{self._counter:06d}"
        self.requests[link_id] = request
        state = LinkState(
            provider_link_id=link_id,
            short_url=f"https://pay.example.test/{link_id}",
            status=CREATED,
            raw={"id": link_id, "reference_id": request.reference_id},
            amount_paise=request.amount_paise,
            currency=request.currency,
            expires_at=request.expire_by,
        )
        self.links[link_id] = state
        return state

    def fetch_link(self, provider_link_id: str) -> LinkState:
        self._record("fetch_link", provider_link_id)
        return self._get(provider_link_id)

    def cancel_link(self, provider_link_id: str) -> LinkState:
        self._record("cancel_link", provider_link_id)
        state = self._get(provider_link_id)
        if state.status == CREATED:
            state = self.set_state(provider_link_id, status=CANCELLED)
        return state

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> list[WebhookLinkUpdate]:
        self._record("parse_webhook")
        if lower_headers(headers).get(SIGNATURE_HEADER) != VALID_SIGNATURE:
            raise InvalidWebhookSignature()
        data = json.loads(body)
        link_id = data["provider_link_id"]
        state = self.links.get(link_id) if data.get("include_state", True) else None
        return [
            WebhookLinkUpdate(
                event_id=data["event_id"],
                event_type=data.get("event_type", ""),
                provider_link_id=link_id,
                state=state,
            )
        ]
