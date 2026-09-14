from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from common.models import TenantScopedModel


class MessageTemplate(TenantScopedModel):
    """A WhatsApp message template, local draft or mirrored from Meta.

    ``components`` is stored in Meta's format. ``workspace`` always equals ``waba.workspace``.
    """

    class Category(models.TextChoices):
        MARKETING = "MARKETING", "Marketing"
        UTILITY = "UTILITY", "Utility"
        AUTHENTICATION = "AUTHENTICATION", "Authentication"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"  # local only, never sent to Meta
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PAUSED = "PAUSED", "Paused"
        DISABLED = "DISABLED", "Disabled"
        IN_APPEAL = "IN_APPEAL", "In appeal"
        PENDING_DELETION = "PENDING_DELETION", "Pending deletion"
        DELETED = "DELETED", "Deleted"
        LIMIT_EXCEEDED = "LIMIT_EXCEEDED", "Limit exceeded"
        ARCHIVED = "ARCHIVED", "Archived"

    class QualityScore(models.TextChoices):
        # Labels deliberately differ from PhoneNumber.QualityRating: spectacular keys enum name
        # overrides by (value, label), so identical choices would collide.
        GREEN = "GREEN", "Green"
        YELLOW = "YELLOW", "Yellow"
        RED = "RED", "Red"
        UNKNOWN = "UNKNOWN", "Not yet rated"

    EDITABLE_STATUSES = frozenset({Status.DRAFT, Status.REJECTED})

    waba = models.ForeignKey(
        "whatsapp.WhatsAppBusinessAccount", on_delete=models.CASCADE, related_name="templates"
    )
    meta_template_id = models.CharField(max_length=64, blank=True, db_index=True)
    name = models.CharField(max_length=512)
    language = models.CharField(max_length=16)
    category = models.CharField(max_length=32, choices=Category.choices)
    previous_category = models.CharField(max_length=32, choices=Category.choices, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    rejected_reason = models.CharField(max_length=255, blank=True)
    quality_score = models.CharField(
        max_length=16, choices=QualityScore.choices, default=QualityScore.UNKNOWN
    )
    components = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["meta_template_id"],
                condition=~Q(meta_template_id=""),
                name="message_templates_unique_meta_template_id",
            ),
            models.UniqueConstraint(
                fields=["waba", "name", "language"],
                name="message_templates_unique_waba_name_language",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.language})"

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    def clean(self) -> None:
        super().clean()
        if self.waba_id and self.workspace_id and self.waba.workspace_id != self.workspace_id:
            raise ValidationError(
                {"waba": "The WhatsApp Business Account belongs to a different workspace."}
            )
