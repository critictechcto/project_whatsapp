"""Payment gateway providers. Get one with :func:`get_provider`; tests swap in a
:class:`~apps.payments.providers.fake.FakePaymentProvider` with :func:`override_provider`."""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from ..exceptions import PaymentAccountMissing
from .base import (
    CANCELLED,
    CREATED,
    EXPIRED,
    PAID,
    PARTIALLY_PAID,
    InvalidWebhookSignature,
    LinkRequest,
    LinkState,
    PaymentProvider,
    WebhookLinkUpdate,
)
from .cashfree import CashfreeProvider
from .razorpay import RazorpayProvider

__all__ = (
    "CANCELLED",
    "CREATED",
    "EXPIRED",
    "PAID",
    "PARTIALLY_PAID",
    "CashfreeProvider",
    "InvalidWebhookSignature",
    "LinkRequest",
    "LinkState",
    "PaymentProvider",
    "RazorpayProvider",
    "WebhookLinkUpdate",
    "get_provider",
    "override_provider",
)

_override: PaymentProvider | None = None


def get_provider(account, *, transport: httpx.BaseTransport | None = None) -> PaymentProvider:
    """The provider for a ``PaymentAccount`` (its own keys), or the test override."""
    if _override is not None:
        return _override
    if account.provider == "razorpay":
        return RazorpayProvider(
            key_id=account.key_id,
            key_secret=account.key_secret,
            webhook_secret=account.webhook_secret,
            transport=transport,
        )
    if account.provider == "cashfree":
        return CashfreeProvider(
            client_id=account.key_id,
            client_secret=account.key_secret,
            mode=account.mode,
            transport=transport,
        )
    raise PaymentAccountMissing()


@contextmanager
def override_provider(provider: PaymentProvider) -> Iterator[PaymentProvider]:
    global _override
    previous = _override
    _override = provider
    try:
        yield provider
    finally:
        _override = previous
