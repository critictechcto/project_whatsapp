"""The payment provider interface (docs/contracts/wave-3-commerce.md, "Providers").

Our code uses integer paise everywhere; rupee conversion happens only inside a provider, with
:func:`rupees_to_paise` / :func:`paise_to_rupees` (``Decimal``, never float arithmetic).

``LinkState`` carries three optional fields beyond the contract (``amount_paise``, ``currency``
and ``expires_at``) so services can check that a paid link matches the amount and currency we
asked for. Adding them is additive; the contract fields keep their names and meaning.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Protocol

# Normalized link statuses reported by every provider.
CREATED = "created"  # open: the buyer can still pay
PAID = "paid"  # paid in full on the gateway
PARTIALLY_PAID = "partially_paid"  # never confirms an order
EXPIRED = "expired"
CANCELLED = "cancelled"
LINK_STATUSES = (CREATED, PAID, PARTIALLY_PAID, EXPIRED, CANCELLED)

# Keys dropped from gateway responses before they are stored in ``PaymentLink.raw``.
_DROPPED_RAW_KEYS = frozenset({"link_qrcode", "payment_session_id"})


@dataclass(frozen=True, slots=True)
class LinkRequest:
    reference_id: str  # <order number>-<attempt>, <= 40 characters
    amount_paise: int
    currency: str
    description: str
    customer_name: str
    customer_phone_e164: str
    expire_by: datetime
    return_url: str
    notes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LinkState:
    provider_link_id: str
    short_url: str
    status: str  # one of LINK_STATUSES
    amount_paid_paise: int = 0
    provider_payment_id: str = ""
    paid_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
    # Additive: what the gateway says the link is for, to check against our row.
    amount_paise: int | None = None
    currency: str = ""
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WebhookLinkUpdate:
    event_id: str
    event_type: str
    provider_link_id: str
    state: LinkState | None  # None: refresh the link from the gateway instead


class InvalidWebhookSignature(Exception):
    """The webhook signature is missing or does not match the raw body."""


class PaymentProvider(Protocol):
    name: str

    def verify_credentials(self) -> None:
        """One cheap authenticated read. Raises ``PaymentAccountInvalid`` on 401/403."""

    def create_link(self, request: LinkRequest) -> LinkState:
        """Create a link; idempotent on ``reference_id``."""

    def fetch_link(self, provider_link_id: str) -> LinkState: ...

    def cancel_link(self, provider_link_id: str) -> LinkState:
        """Cancel an open link; a paid (or already closed) link is returned as it is."""

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> list[WebhookLinkUpdate]:
        """Verify the signature on the raw body first; raises ``InvalidWebhookSignature``."""


# --- Helpers ---------------------------------------------------------------------------------


def rupees_to_paise(value: object) -> int | None:
    """``"249.50"`` / ``249.5`` / ``249`` rupees → ``24950`` paise; None when not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees(paise: int) -> Decimal:
    """``24950`` → ``Decimal("249.50")``."""
    return (Decimal(int(paise)) / 100).quantize(Decimal("0.01"))


def lower_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def body_digest(body: bytes) -> str:
    """Event id fallback when the gateway sends none."""
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


def clean_raw(data: object) -> dict[str, Any]:
    """A gateway entity safe and small enough to keep in ``PaymentLink.raw``."""
    if not isinstance(data, Mapping):
        return {}
    return {str(key): value for key, value in data.items() if key not in _DROPPED_RAW_KEYS}
