from django.db import models

from common.models import UUIDTimeStampedModel


class WebhookEvent(UUIDTimeStampedModel):
    """One verified Meta webhook delivery, stored before processing.

    Not tenant-scoped: the workspace is only known after routing, and one batched delivery can in
    theory touch several workspaces (``workspace`` is the first one routed).
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        UNROUTABLE = "unroutable", "Unroutable"
        FAILED = "failed", "Failed"

    object_type = models.CharField(max_length=64, blank=True)
    body_sha256 = models.CharField(max_length=64, unique=True)
    payload = models.JSONField()
    workspace = models.ForeignKey(
        "tenants.Workspace",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta(UUIDTimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["status", "created_at"], name="webhooks_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.object_type or 'webhook'} {self.body_sha256[:12]} ({self.status})"
