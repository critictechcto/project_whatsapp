from django.conf import settings
from django.db import models
from django.db.models import Q

from common.fields import EncryptedTextField
from common.models import TenantScopedModel


class WhatsAppBusinessAccount(TenantScopedModel):
    """A customer's WABA connected through Embedded Signup. One WABA belongs to one workspace."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        RESTRICTED = "restricted", "Restricted"
        DISABLED = "disabled", "Disabled"
        DISCONNECTED = "disconnected", "Disconnected"

    class OnboardingStatus(models.TextChoices):
        CODE_EXCHANGED = "code_exchanged", "Code exchanged"
        SUBSCRIBING = "subscribing", "Subscribing to webhooks"
        REGISTERING = "registering", "Registering phone number"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    waba_id = models.CharField(max_length=64, unique=True)
    business_id = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=8, blank=True)
    timezone_id = models.CharField(max_length=16, blank=True)
    message_template_namespace = models.CharField(max_length=128, blank=True)
    access_token = EncryptedTextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    onboarding_status = models.CharField(
        max_length=16, choices=OnboardingStatus.choices, default=OnboardingStatus.CODE_EXCHANGED
    )
    last_error = models.TextField(blank=True)
    subscribed_at = models.DateTimeField(null=True, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta(TenantScopedModel.Meta):
        verbose_name = "WhatsApp Business Account"

    def __str__(self) -> str:
        return self.name or self.waba_id


class PhoneNumber(TenantScopedModel):
    """A business phone number on a WABA. ``workspace`` always equals ``waba.workspace``."""

    class QualityRating(models.TextChoices):
        GREEN = "GREEN", "High"
        YELLOW = "YELLOW", "Medium"
        RED = "RED", "Low"
        UNKNOWN = "UNKNOWN", "Unknown"

    class RegistrationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        REGISTERED = "registered", "Registered"
        FAILED = "failed", "Failed"
        DEREGISTERED = "deregistered", "Deregistered"

    waba = models.ForeignKey(
        WhatsAppBusinessAccount, on_delete=models.CASCADE, related_name="phone_numbers"
    )
    phone_number_id = models.CharField(max_length=64, unique=True)
    display_phone_number = models.CharField(max_length=32)
    phone_e164 = models.CharField(max_length=20, blank=True)
    verified_name = models.CharField(max_length=255, blank=True)
    name_status = models.CharField(max_length=32, blank=True)
    quality_rating = models.CharField(
        max_length=16, choices=QualityRating.choices, default=QualityRating.UNKNOWN
    )
    # Meta tier strings such as TIER_250, TIER_1K, TIER_10K, TIER_100K, TIER_UNLIMITED.
    messaging_limit_tier = models.CharField(max_length=32, blank=True)
    throughput_level = models.CharField(max_length=32, blank=True)
    platform_type = models.CharField(max_length=32, blank=True)
    code_verification_status = models.CharField(max_length=32, blank=True)
    meta_status = models.CharField(max_length=32, blank=True)
    registration_status = models.CharField(
        max_length=16, choices=RegistrationStatus.choices, default=RegistrationStatus.PENDING
    )
    # Number also used in the WhatsApp Business app (coexistence onboarding): never register.
    is_coexistence = models.BooleanField(default=False)
    pin = EncryptedTextField(blank=True)
    is_default = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["workspace"],
                condition=Q(is_default=True),
                name="whatsapp_one_default_phone_per_workspace",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_phone_number} ({self.verified_name or self.phone_number_id})"
