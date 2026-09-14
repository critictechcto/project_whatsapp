import secrets
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions

from common.exceptions import Conflict
from common.roles import Role, role_at_least
from common.tenancy import InsufficientRole

from .models import Invitation, Membership, Workspace


class LastOwner(Conflict):
    default_code = "last_owner"
    default_detail = "A workspace must keep at least one owner."


def _unique_slug(name: str) -> str:
    base = slugify(name)[:50] or "workspace"
    slug = base
    while Workspace.objects.filter(slug=slug).exists():
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


@transaction.atomic
def create_workspace(*, user, name: str, time_zone: str | None = None) -> Workspace:
    workspace = Workspace.objects.create(
        name=name,
        slug=_unique_slug(name),
        time_zone=time_zone or settings.TIME_ZONE,
        created_by=user,
    )
    Membership.objects.create(workspace=workspace, user=user, role=Role.OWNER)
    return workspace


def _ensure_not_last_owner(membership: Membership) -> None:
    owner_ids = list(
        Membership.objects.select_for_update()
        .filter(workspace_id=membership.workspace_id, role=Role.OWNER)
        .values_list("pk", flat=True)
    )
    if owner_ids == [membership.pk]:
        raise LastOwner()


@transaction.atomic
def change_member_role(*, actor: Membership, membership: Membership, role: str) -> Membership:
    if membership.role == role:
        return membership
    if Role.OWNER in (role, membership.role) and actor.role != Role.OWNER:
        raise InsufficientRole("Only owners can grant or remove the owner role.")
    if membership.role == Role.OWNER:
        _ensure_not_last_owner(membership)
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    return membership


@transaction.atomic
def remove_member(*, actor: Membership, membership: Membership) -> None:
    """Admins remove others (owners only by owners); anyone may leave. The last owner stays."""
    if membership.user_id != actor.user_id:
        if not role_at_least(actor.role, Role.ADMIN):
            raise InsufficientRole("Only admins can remove other members.")
        if membership.role == Role.OWNER and actor.role != Role.OWNER:
            raise InsufficientRole("Only owners can remove an owner.")
    if membership.role == Role.OWNER:
        _ensure_not_last_owner(membership)
    membership.delete()


def create_invitation(
    *, workspace: Workspace, invited_by: Membership, email: str, role: str
) -> Invitation:
    """Create an invitation and email its one-time link. Replaces any open invite to the email."""
    email = email.strip().lower()
    if role == Role.OWNER and invited_by.role != Role.OWNER:
        raise InsufficientRole("Only owners can invite owners.")
    if Membership.objects.filter(workspace=workspace, user__email__iexact=email).exists():
        raise Conflict("This person is already a member of the workspace.")

    raw_token = secrets.token_urlsafe(32)
    now = timezone.now()
    with transaction.atomic():
        Invitation.objects.open().filter(workspace=workspace, email__iexact=email).update(
            revoked_at=now
        )
        invitation = Invitation.objects.create(
            workspace=workspace,
            email=email,
            role=role,
            token_hash=Invitation.hash_token(raw_token),
            invited_by=invited_by.user,
            expires_at=now + timedelta(days=settings.INVITATION_TTL_DAYS),
        )
        transaction.on_commit(partial(send_invitation_email, invitation, raw_token))
    return invitation


def send_invitation_email(invitation: Invitation, raw_token: str) -> None:
    inviter = invitation.invited_by.get_full_name() if invitation.invited_by else "A teammate"
    link = f"{settings.FRONTEND_URL.rstrip('/')}/invitations/accept?token={raw_token}"
    send_mail(
        subject=f"You're invited to {invitation.workspace.name} on UpChatz",
        message=(
            f"{inviter} invited you to join {invitation.workspace.name} as {invitation.role}.\n\n"
            f"Accept the invitation: {link}\n\n"
            f"This link expires on {timezone.localtime(invitation.expires_at):%d %b %Y}."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
    )


def revoke_invitation(invitation: Invitation) -> None:
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at", "updated_at"])


@transaction.atomic
def accept_invitation(*, raw_token: str, user) -> Membership:
    invitation = (
        Invitation.objects.select_for_update()
        .select_related("workspace")
        .filter(token_hash=Invitation.hash_token(raw_token), workspace__is_active=True)
        .first()
    )
    if invitation is None or invitation.status != Invitation.Status.PENDING:
        raise exceptions.ValidationError(
            {"token": ["This invitation is invalid or has expired."]}, code="invitation_invalid"
        )
    if invitation.email.lower() != user.email.lower():
        raise exceptions.PermissionDenied("This invitation was sent to a different email address.")

    membership, _ = Membership.objects.get_or_create(
        workspace=invitation.workspace, user=user, defaults={"role": invitation.role}
    )
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    return membership
