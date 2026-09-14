"""Campaigns: bulk template sends to an audience of contacts, one recipient row per contact.

Campaign status machine::

    draft --launch--> running                       (send now)
    draft --launch--> scheduled --start_due--> running
    scheduled | running --pause (API or Meta event)--> paused --resume--> running | scheduled
    scheduled | running | paused --cancel--> cancelled
    running --nothing pending or queued--> completed  (failed when nothing was sent)

Recipients are materialised at launch. Their status moves pending -> queued (a queued inbox
Message exists) -> sent -> delivered -> read, or ends skipped/failed. ``failed`` is terminal
unless Meta later reports delivered/read.
"""

from django.conf import settings
from django.db import models

from common.models import TenantScopedModel

ESTIMATE_NOTE = (
    "Estimate under Meta's current pricing; Meta bills your WhatsApp Business Account directly."
)


class Campaign(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        RUNNING = "running", "Running"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"

    EDITABLE_STATUSES = frozenset({Status.DRAFT, Status.SCHEDULED})
    PAUSABLE_STATUSES = frozenset({Status.SCHEDULED, Status.RUNNING})
    CANCELLABLE_STATUSES = frozenset({Status.SCHEDULED, Status.RUNNING, Status.PAUSED})

    # CampaignStats key -> counter field. ``sent`` counts recipients that reached sent or later,
    # ``delivered`` delivered or read; ``queued``, ``skipped`` and ``failed`` are current states.
    STAT_FIELDS = {
        "total": "total_count",
        "skipped": "skipped_count",
        "queued": "queued_count",
        "sent": "sent_count",
        "delivered": "delivered_count",
        "read": "read_count",
        "failed": "failed_count",
        "replied": "replied_count",
    }

    name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # ``{id, name, language, category}`` so the campaign still names its template after deletion.
    template_snapshot = models.JSONField(default=dict, blank=True)
    phone_number = models.ForeignKey(
        "whatsapp.PhoneNumber", on_delete=models.CASCADE, related_name="+"
    )
    audience = models.JSONField(default=dict, blank=True)  # {tag_ids, match, contact_ids}
    variable_mapping = models.JSONField(default=dict, blank=True)  # {body, header, buttons}

    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    consent_attested = models.BooleanField(default=False)
    attested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    attested_at = models.DateTimeField(null=True, blank=True)

    estimated_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    total_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    queued_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    read_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    replied_count = models.PositiveIntegerField(default=0)

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["workspace", "status"], name="campaigns_ws_status_idx"),
            models.Index(fields=["status", "scheduled_at"], name="campaigns_status_sched_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"

    @property
    def stats(self) -> dict[str, int]:
        return {key: getattr(self, field) for key, field in self.STAT_FIELDS.items()}

    @property
    def template_summary(self) -> dict | None:
        template = self.template
        if template is not None:
            return {
                "id": template.pk,
                "name": template.name,
                "language": template.language,
                "category": template.category,
            }
        return self.template_snapshot or None

    @property
    def estimated_cost_summary(self) -> dict | None:
        if self.estimated_cost is None:
            return None
        return {"currency": "INR", "amount": self.estimated_cost, "note": ESTIMATE_NOTE}


class CampaignRecipient(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SKIPPED = "skipped", "Skipped"
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"

    class SkipReason(models.TextChoices):
        OPTED_OUT = "opted_out", "Opted out"
        NOT_OPTED_IN = "not_opted_in", "No marketing opt-in"
        INVALID = "invalid", "Invalid WhatsApp number"
        MISSING_VARIABLE = "missing_variable", "Missing variable value"
        CANCELLED = "cancelled", "Campaign cancelled"
        # Set on failed recipients: Meta error 131049 (per-user marketing message limit).
        PER_USER_MARKETING_LIMIT = "per_user_marketing_limit", "Meta per-user marketing limit"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    contact = models.ForeignKey("contacts.Contact", on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    skip_reason = models.CharField(max_length=32, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    message = models.ForeignKey(
        "inbox.Message", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Resolved template parameters: {"body": [str], "header": str | None, "buttons": {"0": str}}.
    params = models.JSONField(default=dict, blank=True)

    # Consent snapshot at materialisation; consent is checked again before each send.
    consent_status = models.CharField(max_length=16, blank=True)
    consent_opted_in_at = models.DateTimeField(null=True, blank=True)
    consent_opted_out_at = models.DateTimeField(null=True, blank=True)

    queued_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "contact"], name="campaigns_recipient_unique_contact"
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "status"], name="campaigns_rcpt_status_idx"),
            models.Index(fields=["workspace", "message"], name="campaigns_rcpt_message_idx"),
            models.Index(
                fields=["workspace", "contact", "sent_at"], name="campaigns_rcpt_contact_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"Recipient {self.contact_id} of campaign {self.campaign_id} ({self.status})"
