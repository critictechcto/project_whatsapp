"""Seller alerts: order alerts sent to sellers' personal WhatsApp from the UpChatz number.

``AlertMessage`` is the platform number's outbound log. It is platform-level (not a workspace
inbox message) and never appears in a workspace inbox.
"""

from django.db import models

from common.models import TenantScopedModel, UUIDTimeStampedModel

MAX_RECIPIENTS_PER_WORKSPACE = 3
ALL_ALERT_EVENTS = ("new_order", "needs_attention", "order_cancelled")


def default_alert_events() -> list[str]:
    return list(ALL_ALERT_EVENTS)


class AlertRecipient(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        OPTED_OUT = "opted_out", "Opted out"

    name = models.CharField(max_length=60)
    phone_e164 = models.CharField(max_length=16)
    wa_id = models.CharField(max_length=15, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    events = models.JSONField(default=default_alert_events, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    verification_sent_at = models.DateTimeField(null=True, blank=True)
    # When this phone last messaged the platform number: while that 24-hour customer service
    # window is open, alerts go out as free-form messages instead of paid templates.
    last_inbound_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "phone_e164"], name="seller_alerts_recipient_unique_phone"
            ),
        ]
        indexes = [
            models.Index(fields=["wa_id", "status"], name="seller_alerts_rcpt_wa_idx"),
            models.Index(fields=["workspace", "status"], name="seller_alerts_rcpt_ws_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone_e164}, {self.status})"


class AlertMessage(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        VERIFY = "verify", "Verification"
        NEW_ORDER = "new_order", "New order"
        NEEDS_ATTENTION = "needs_attention", "Needs attention"
        ORDER_CANCELLED = "order_cancelled", "Order cancelled"
        REPLY = "reply", "Command reply"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"

    recipient = models.ForeignKey(
        AlertRecipient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    workspace = models.ForeignKey(
        "tenants.Workspace", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    to_wa_id = models.CharField(max_length=15, blank=True)
    wamid = models.CharField(max_length=128, unique=True, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    # "<recipient>:<order>:<event>:<new_status>" for order alerts, so an alert goes out once.
    dedupe_key = models.CharField(max_length=160, unique=True, null=True, blank=True)

    class Meta(UUIDTimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["status", "created_at"], name="seller_alerts_msg_status_idx"),
            models.Index(fields=["recipient", "created_at"], name="seller_alerts_msg_rcpt_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} to {self.to_wa_id} ({self.status})"


class PendingSellerReply(TenantScopedModel):
    """A question the platform number asked a seller, e.g. the courier and AWB after *Mark
    shipped*. A bare reply from that recipient applies to this order until it expires."""

    class Action(models.TextChoices):
        AWAITING_AWB = "awaiting_awb", "Awaiting courier and AWB"

    recipient = models.ForeignKey(
        AlertRecipient, on_delete=models.CASCADE, related_name="pending_replies"
    )
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="+")
    action = models.CharField(max_length=24, choices=Action.choices)
    prompt_wamid = models.CharField(max_length=128, blank=True)
    expires_at = models.DateTimeField()

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["recipient", "expires_at"], name="seller_alerts_pending_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} for {self.order_id}"


class AlertInboundMessage(UUIDTimeStampedModel):
    """A message the platform number received. Keyed on ``wamid`` so webhook retries are
    handled once; also the log of messages from unknown or unverified senders."""

    class Outcome(models.TextChoices):
        HANDLED = "handled", "Handled"
        IGNORED = "ignored", "Ignored (unknown or unverified sender)"

    wamid = models.CharField(max_length=128, unique=True)
    from_wa_id = models.CharField(max_length=32, db_index=True)
    type = models.CharField(max_length=32, blank=True)
    text = models.TextField(blank=True)
    reply_id = models.CharField(max_length=256, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, default=Outcome.HANDLED)
    received_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.type} from {self.from_wa_id} ({self.outcome})"
