"""Payments services (docs/contracts/wave-3-commerce.md, "Payments services").

Signatures are frozen by the contract. ``get_account`` and ``online_payments_ready`` are
implemented; link creation and cancellation are stubs that the B-phase agents implement.
"""

from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.urls import reverse

from .exceptions import PaymentAccountInvalid, PaymentAccountMissing
from .models import PaymentAccount, PaymentLink

__all__ = [
    "PaymentAccountInvalid",
    "PaymentAccountMissing",
    "cancel_payment_link",
    "create_payment_link",
    "get_account",
    "online_payments_ready",
    "webhook_url",
]


def get_account(workspace) -> PaymentAccount | None:
    return PaymentAccount.objects.filter(workspace=workspace).first()


def online_payments_ready(workspace) -> bool:
    """True when the workspace has verified Razorpay keys and a webhook secret."""
    account = get_account(workspace)
    return bool(
        account is not None
        and account.status == PaymentAccount.Status.VERIFIED
        and account.key_id
        and account.key_secret
        and account.webhook_secret
    )


def webhook_url(account: PaymentAccount) -> str:
    """Absolute URL the seller enters in Razorpay; "" for an account that isn't saved yet."""
    if account.pk is None or account._state.adding or not account.webhook_token:
        return ""
    path = reverse("payments_webhooks:merchant-webhook", args=[account.webhook_token])
    return f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}{path}"


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
    """Create a Razorpay Payment Link on the seller's account; idempotent on ``reference_id``.

    Raises :class:`PaymentAccountMissing` / :class:`PaymentAccountInvalid` (409) or
    ``common.razorpay.RazorpayError`` (retryable).
    """
    raise NotImplementedError


def cancel_payment_link(payment_link: PaymentLink) -> PaymentLink:
    """Cancel an open link; idempotent, and never cancels a paid link."""
    raise NotImplementedError
