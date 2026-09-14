from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from common.models import TenantScopedModel, TenantScopedQuerySet

MAX_IMPORT_ERRORS = 100

hex_color_validator = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a hex color such as #25D366.")


class Tag(TenantScopedModel):
    name = models.CharField(max_length=64)
    color = models.CharField(max_length=7, blank=True, validators=[hex_color_validator])

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("name"), F("workspace"), name="contacts_tag_unique_name_ci"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ContactQuerySet(TenantScopedQuerySet):
    def marketing_allowed(self):
        """Contacts with a recorded marketing opt-in (see services.is_marketing_allowed)."""
        return self.filter(marketing_opt_in_status=Contact.OptInStatus.OPTED_IN)


class Contact(TenantScopedModel):
    """A WhatsApp user a workspace can message. Consent changes go through ``services``."""

    class OptInStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        OPTED_IN = "opted_in", "Opted in"
        OPTED_OUT = "opted_out", "Opted out"

    phone_e164 = models.CharField(max_length=16)
    wa_id = models.CharField(max_length=15, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    tags = models.ManyToManyField(Tag, related_name="contacts", blank=True)
    marketing_opt_in_status = models.CharField(
        max_length=16, choices=OptInStatus.choices, default=OptInStatus.UNKNOWN
    )
    opted_in_at = models.DateTimeField(null=True, blank=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)
    opt_in_source = models.CharField(max_length=32, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)

    objects = ContactQuerySet.as_manager()

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "phone_e164"], name="contacts_contact_unique_phone"
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "marketing_opt_in_status"], name="contacts_ws_opt_in_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone_e164})" if self.name else self.phone_e164


class ConsentEvent(TenantScopedModel):
    """Append-only audit trail of marketing consent changes for a contact."""

    class Purpose(models.TextChoices):
        MARKETING = "marketing", "Marketing"

    class Action(models.TextChoices):
        OPT_IN = "opt_in", "Opt in"
        OPT_OUT = "opt_out", "Opt out"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Import"
        API = "api", "API"
        WHATSAPP_KEYWORD = "whatsapp_keyword", "WhatsApp keyword"
        META_MARKETING_OPTOUT = "meta_marketing_optout", "Meta marketing opt-out"

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="consent_events")
    purpose = models.CharField(max_length=16, choices=Purpose.choices, default=Purpose.MARKETING)
    action = models.CharField(max_length=16, choices=Action.choices)
    source = models.CharField(max_length=32, choices=Source.choices)
    evidence = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    wamid = models.CharField(max_length=255, blank=True, db_index=True)
    occurred_at = models.DateTimeField()

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["contact", "wamid"],
                condition=~Q(wamid=""),
                name="contacts_consentevent_unique_wamid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} via {self.get_source_display()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Consent events are append-only and cannot be changed.")
        super().save(*args, **kwargs)


class ContactImport(TenantScopedModel):
    """A CSV upload processed by the ``contacts.import_csv`` task.

    ``created_count``/``updated_count`` count distinct contacts; duplicate rows in the file merge
    into one contact. ``skipped_count`` counts opted-out contacts that were not opted in again.
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    file = models.FileField(upload_to="contact_imports/%Y/%m/")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    mark_opted_in = models.BooleanField(default=False)
    consent_attested = models.BooleanField(default=False)
    opt_in_source = models.CharField(max_length=255, blank=True)
    tags = models.ManyToManyField(Tag, related_name="imports", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        pass

    def __str__(self) -> str:
        return f"Contact import {self.pk} ({self.status})"
