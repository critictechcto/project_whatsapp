import secrets
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions

from apps.billing import entitlements
from common.events import (
    MembershipRemoved,
    MembershipRoleChanged,
    WorkspaceCreated,
    emit,
    membership_removed,
    membership_role_changed,
    workspace_created,
)
from common.exceptions import Conflict
from common.roles import Role, role_at_least
from common.tenancy import InsufficientRole

from .models import Invitation, Membership, Workspace
from .tasks import send_invitation_email


class LastOwner(Conflict):
    default_code = "last_owner"
    default_detail = "A workspace must keep at least one owner."


def _emit_on_commit(signal, event) -> None:
    transaction.on_commit(partial(emit, signal, event))


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
    _emit_on_commit(
        workspace_created, WorkspaceCreated(workspace_id=workspace.pk, owner_id=user.pk)
    )
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
    old_role = membership.role
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    _emit_on_commit(
        membership_role_changed,
        MembershipRoleChanged(
            workspace_id=membership.workspace_id,
            user_id=membership.user_id,
            old_role=old_role,
            new_role=role,
        ),
    )
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
    event = MembershipRemoved(workspace_id=membership.workspace_id, user_id=membership.user_id)
    membership.delete()
    _emit_on_commit(membership_removed, event)


def _lock_workspace(workspace: Workspace) -> None:
    """Serialise member-quota checks per workspace until the transaction ends."""
    list(Workspace.objects.select_for_update().filter(pk=workspace.pk).values_list("pk"))


def pending_invitation_count(workspace: Workspace, *, exclude_email: str = "") -> int:
    """Open, unexpired invitations; they reserve a member seat until accepted or revoked."""
    queryset = Invitation.objects.open().filter(workspace=workspace, expires_at__gt=timezone.now())
    if exclude_email:
        queryset = queryset.exclude(email__iexact=exclude_email)
    return queryset.count()


def check_member_quota_for_invitation(workspace: Workspace, *, email: str) -> None:
    """Members plus pending invitations (other than one being replaced) plus this one must fit
    the plan's member limit. Raises ``QuotaExceeded`` (409 ``quota_exceeded``)."""
    pending = pending_invitation_count(workspace, exclude_email=email)
    try:
        entitlements.check_quota(workspace, entitlements.MEMBERS, amount=1 + pending)
    except entitlements.QuotaExceeded as exc:
        if not pending or exc.metric is None:
            raise
        noun = "invitation counts" if pending == 1 else "invitations count"
        raise entitlements.QuotaExceeded(
            f"{exc} {pending} pending {noun} toward the limit; revoke one to invite someone else.",
            metric=exc.metric,
            limit=exc.limit,
            used=exc.used,
        ) from None


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
        _lock_workspace(workspace)
        check_member_quota_for_invitation(workspace, email=email)
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
        transaction.on_commit(
            partial(send_invitation_email.delay, str(invitation.pk), raw_token), robust=True
        )
    return invitation


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

    workspace = invitation.workspace
    _lock_workspace(workspace)
    membership = Membership.objects.filter(workspace=workspace, user=user).first()
    if membership is None:
        # Re-checked here: the plan may have changed, or members joined another way, since the
        # invitation was sent. The accepted invitation's own seat is this new member.
        entitlements.check_quota(workspace, entitlements.MEMBERS)
        membership = Membership.objects.create(workspace=workspace, user=user, role=invitation.role)
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    if user.email_verified_at is None:
        # The invitation link was mailed to this address, so opening it proves inbox control.
        user.email_verified_at = invitation.accepted_at
        user.save(update_fields=["email_verified_at"])
    return membership
