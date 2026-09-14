"""Payments: each seller's own payment gateway account (Razorpay or Cashfree) and the payment
links created on it.

Secrets (``key_secret``, ``webhook_secret``) are encrypted at rest and never serialized or
logged. Payments are confirmed without any seller webhook setup: the buyer's return to
``/pay/return/<payment_link_id>/`` and ``payments.poll_open_links`` both re-fetch the link from
the gateway. An optional webhook reaches ``/webhooks/payments/merchants/<webhook_token>/``.
"""

import secrets

from django.db import models

from common.fields import EncryptedTextField
from common.models import TenantScopedModel, UUIDTimeStampedModel

CURRENCY = "INR"
WEBHOOK_EVENTS = {
    "razorpay": (
        "payment_link.paid",
        "payment_link.partially_paid",
        "payment_link.expired",
        "payment_link.cancelled",
    ),
    "cashfree": ("PAYMENT_LINK_EVENT",),
}
RAZORPAY_TEST_KEY_PREFIX = "rzp_test_"
RAZORPAY_LIVE_KEY_PREFIX = "rzp_live_"


def new_webhook_token() -> str:
    return secrets.token_urlsafe(32)


class PaymentAccount(UUIDTimeStampedModel):
    class Provider(models.TextChoices):
        RAZORPAY = "razorpay", "Razorpay"
        CASHFREE = "cashfree", "Cashfree"

    class Mode(models.TextChoices):
        TEST = "test", "Test"
        LIVE = "live", "Live"

    class Status(models.TextChoices):
        NOT_CONFIGURED = "not_configured", "Not configured"
        UNVERIFIED = "unverified", "Unverified"
        VERIFIED = "verified", "Verified"
        INVALID = "invalid", "Invalid"

    workspace = models.OneToOneField(
        "tenants.Workspace", on_delete=models.CASCADE, related_name="payment_account"
    )
    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.RAZORPAY)
    mode = models.CharField(max_length=8, choices=Mode.choices, blank=True)
    # Razorpay key id or Cashfree App ID (client id).
    key_id = models.CharField(max_length=100, blank=True)
    key_secret = EncryptedTextField(blank=True)
    # Razorpay only; Cashfree signs webhooks with the secret key.
    webhook_secret = EncryptedTextField(blank=True)
    webhook_token = models.CharField(max_length=64, unique=True, default=new_webhook_token)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_CONFIGURED)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta(UUIDTimeStampedModel.Meta):
        pass

    def __str__(self) -> str:
        return f"{self.provider} account for {self.workspace_id} ({self.status})"

    @property
    def has_key_secret(self) -> bool:
        return bool(self.key_secret)

    @property
    def has_webhook_secret(self) -> bool:
        return bool(self.webhook_secret)


class PaymentLink(TenantScopedModel):
    """A payment link for one checkout attempt of an order (an outbox row: saved ``creating``
    before the provider call)."""

    class Status(models.TextChoices):
        CREATING = "creating", "Creating"
        CREATED = "created", "Created"
        PAID = "paid", "Paid"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"

    OPEN_STATUSES = frozenset({Status.CREATING, Status.CREATED})

    order = models.ForeignKey(
        "orders.Order", on_delete=models.CASCADE, related_name="payment_links"
    )
    provider = models.CharField(
        max_length=16,
        choices=PaymentAccount.Provider.choices,
        default=PaymentAccount.Provider.RAZORPAY,
    )
    provider_link_id = models.CharField(max_length=100, blank=True)
    reference_id = models.CharField(max_length=40)
    short_url = models.URLField(max_length=255, blank=True)
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default=CURRENCY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATING)
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    provider_payment_id = models.CharField(max_length=100, blank=True)
    # Status polling (payments.poll_open_links), so no seller webhook is required.
    next_poll_at = models.DateTimeField(null=True, blank=True)
    poll_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "reference_id"], name="payments_link_unique_reference"
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "status"], name="payments_link_ws_status_idx"),
            models.Index(fields=["order", "created_at"], name="payments_link_order_idx"),
            models.Index(fields=["provider_link_id"], name="payments_link_provider_idx"),
            models.Index(fields=["status", "next_poll_at"], name="payments_link_poll_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.reference_id} ({self.status})"


class PaymentWebhookEvent(TenantScopedModel):
    """A verified optional merchant webhook delivery, recorded once per gateway event id."""

    event_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "event_id"], name="payments_webhook_unique_event"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type or 'event'} {self.event_id}"
