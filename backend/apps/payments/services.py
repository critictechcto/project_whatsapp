"""Payments services (docs/contracts/wave-3-commerce.md, "Payments services").

Signatures are frozen by the contract. ``get_account``, ``online_payments_ready``,
``webhook_url`` and ``return_url`` are implemented; link creation, cancellation and refresh are
stubs that the B-phase payments agent implements.
"""

from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.urls import reverse

from .exceptions import PaymentAccountInvalid, PaymentAccountMissing, PaymentProviderError
from .models import PaymentAccount, PaymentLink

__all__ = [
    "PaymentAccountInvalid",
    "PaymentAccountMissing",
    "PaymentProviderError",
    "cancel_payment_link",
    "create_payment_link",
    "get_account",
    "online_payments_ready",
    "refresh_payment_link",
    "return_url",
    "webhook_url",
]


def get_account(workspace) -> PaymentAccount | None:
    return PaymentAccount.objects.filter(workspace=workspace).first()


def online_payments_ready(workspace) -> bool:
    """True when the workspace has a verified gateway account with its keys and mode.

    No webhook is needed: payments are confirmed by the buyer's return and by polling.
    """
    account = get_account(workspace)
    return bool(
        account is not None
        and account.status == PaymentAccount.Status.VERIFIED
        and account.key_id
        and account.key_secret
        and account.mode
    )


def _absolute(path: str) -> str:
    return f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}{path}"


def webhook_url(account: PaymentAccount) -> str:
    """Optional webhook URL for the gateway settings; "" for an account that isn't saved yet."""
    if account.pk is None or account._state.adding or not account.webhook_token:
        return ""
    return _absolute(reverse("payments_webhooks:merchant-webhook", args=[account.webhook_token]))


def return_url(payment_link: PaymentLink) -> str:
    """Where the gateway sends the buyer after paying."""
    return _absolute(reverse("payments_return:link-return", args=[payment_link.pk]))


# --- Stubs (B phase) --------------------------------------------------------------------------


def create_payment_link(
    *,
    workspace,
    order_id: UUID,
    reference_id: str,
    amount_paise: int,
    description: str,
    customer_name: str,
    customer_phone_e164: str,
    expire_by: datetime,
) -> PaymentLink:
    """Create a payment link on the seller's gateway account; idempotent on ``reference_id``.

    Raises :class:`PaymentAccountMissing` / :class:`PaymentAccountInvalid` (409) or
    :class:`PaymentProviderError` (check ``retryable``).
    """
    raise NotImplementedError


def cancel_payment_link(payment_link: PaymentLink) -> PaymentLink:
    """Cancel an open link; idempotent, and never cancels a paid link."""
    raise NotImplementedError


def refresh_payment_link(payment_link: PaymentLink) -> PaymentLink:
    """Fetch the link from the gateway and apply its state (emitting payment events once)."""
    raise NotImplementedError
