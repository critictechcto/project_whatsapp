"""Automations: rules that react to inbound WhatsApp messages, business hours and run history.

Rules are evaluated by :mod:`apps.automations.engine` for every inbound message (see
``receivers.py``). Each matched rule leaves one :class:`AutomationRun` per message; the
``(rule, message)`` constraint makes reprocessing a redelivered message a no-op.
"""

from django.db import models

from common.models import TenantScopedModel

from .business_hours import DEFAULT_TIME_ZONE
from .schema_enums import (
    AUTOMATION_RUN_STATUSES,
    AUTOMATION_TRIGGERS,
    KEYWORD_MATCHES,
)


def _choices(values: tuple[str, ...]) -> list[tuple[str, str]]:
    # Labels equal values so drf-spectacular's enum name overrides (value, label) stay unambiguous.
    return [(value, value) for value in values]


class AutomationRule(TenantScopedModel):
    """A trigger plus 1-5 actions. Lower ``priority`` runs first; ties run oldest first.

    ``actions`` is a list of ``{"type": ..., "config": {...}}`` validated by the serializer.
    ``keywords`` are stored normalised (whitespace collapsed, casefolded).
    """

    class Trigger(models.TextChoices):
        KEYWORD = "keyword"
        FIRST_INBOUND = "first_inbound"
        NEW_CONTACT = "new_contact"
        OUTSIDE_BUSINESS_HOURS = "outside_business_hours"

    class KeywordMatch(models.TextChoices):
        EXACT = "exact"
        CONTAINS = "contains"

    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    trigger = models.CharField(max_length=32, choices=_choices(AUTOMATION_TRIGGERS))
    keywords = models.JSONField(default=list, blank=True)  # list[str]
    keyword_match = models.CharField(
        max_length=16, choices=_choices(KEYWORD_MATCHES), default=KeywordMatch.EXACT
    )
    # Null applies the rule to every number; deleting the number deletes rules scoped to it.
    phone_number = models.ForeignKey(
        "whatsapp.PhoneNumber",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="automation_rules",
    )
    actions = models.JSONField(default=list, blank=True)
    cooldown_minutes = models.PositiveIntegerField(default=0)
    priority = models.IntegerField(default=0)
    stop_processing = models.BooleanField(default=False)
    run_count = models.PositiveIntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(
                fields=["workspace", "is_active", "trigger", "priority"],
                name="automations_rule_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.trigger})"


class BusinessHours(TenantScopedModel):
    """One per workspace. ``schedule`` is a list of ``{"day": 0-6, "start": "HH:MM",
    "end": "HH:MM"}`` in the workspace time zone; ``end < start`` runs overnight."""

    enabled = models.BooleanField(default=False)
    schedule = models.JSONField(default=list, blank=True)

    class Meta(TenantScopedModel.Meta):
        verbose_name_plural = "business hours"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace"], name="automations_one_business_hours_per_workspace"
            ),
        ]

    def __str__(self) -> str:
        return f"Business hours for {self.workspace_id}"

    @property
    def time_zone(self) -> str:
        """Schedules are read in the workspace time zone."""
        return self.workspace.time_zone or DEFAULT_TIME_ZONE


class AutomationRun(TenantScopedModel):
    """The outcome of one matched rule for one inbound message.

    ``action_results`` holds one entry per action: ``index``, ``type``, ``status``
    (``succeeded``, ``failed`` or ``not_run``) and optional ``code``, ``message`` and
    ``message_id`` (the outbound message a send action queued).
    """

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded"
        SKIPPED = "skipped"
        FAILED = "failed"

    rule = models.ForeignKey(AutomationRule, on_delete=models.CASCADE, related_name="runs")
    conversation = models.ForeignKey(
        "inbox.Conversation", on_delete=models.CASCADE, related_name="automation_runs"
    )
    message = models.ForeignKey(
        "inbox.Message", on_delete=models.CASCADE, related_name="automation_runs"
    )
    status = models.CharField(max_length=16, choices=_choices(AUTOMATION_RUN_STATUSES))
    detail = models.TextField(blank=True)
    action_results = models.JSONField(default=list, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "message"], name="automations_run_unique_rule_message"
            ),
        ]
        indexes = [
            models.Index(
                fields=["rule", "conversation", "created_at"],
                name="automations_run_cooldown_idx",
            ),
            models.Index(
                fields=["workspace", "status", "created_at"], name="automations_run_ws_status_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"Run of {self.rule_id} for message {self.message_id} ({self.status})"
