import hashlib

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from common.models import UUIDTimeStampedModel
from common.roles import Role


class Workspace(UUIDTimeStampedModel):
    """A tenant: one business account on the platform. Every tenant-owned row points here."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=64, unique=True)
    time_zone = models.CharField(max_length=64, default="Asia/Kolkata")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta(UUIDTimeStampedModel.Meta):
        pass

    def __str__(self) -> str:
        return self.name


class Membership(UUIDTimeStampedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.AGENT)

    class Meta(UUIDTimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="tenants_membership_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.workspace} ({self.role})"


class InvitationQuerySet(models.QuerySet):
    def open(self):
        return self.filter(accepted_at__isnull=True, revoked_at__isnull=True)


class Invitation(UUIDTimeStampedModel):
    """Email invite to join a workspace. Only a SHA-256 hash of the token is stored."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.AGENT)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = InvitationQuerySet.as_manager()

    class Meta(UUIDTimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                F("workspace"),
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="tenants_invitation_one_open_per_email",
            ),
        ]

    def __str__(self) -> str:
        return f"Invitation for {self.email} to {self.workspace}"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @property
    def status(self) -> str:
        if self.accepted_at:
            return self.Status.ACCEPTED
        if self.revoked_at:
            return self.Status.REVOKED
        if self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.Status.PENDING
