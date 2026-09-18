"""Workspace emails."""

from urllib.parse import urlencode

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from common.mail import send_or_retry

from .models import Invitation


def invitation_link(raw_token: str) -> str:
    return (
        f"{settings.FRONTEND_URL.rstrip('/')}/app/invitations/accept?"
        f"{urlencode({'token': raw_token})}"
    )


@shared_task(bind=True, name="tenants.send_invitation_email")
def send_invitation_email(self, invitation_id: str, raw_token: str) -> bool:
    """Email the invitation's one-time link. Skips invitations that are no longer pending."""
    invitation = (
        Invitation.objects.select_related("workspace", "invited_by")
        .filter(pk=invitation_id)
        .first()
    )
    if invitation is None or invitation.status != Invitation.Status.PENDING:
        return False
    inviter = invitation.invited_by.get_full_name() if invitation.invited_by else "A teammate"
    send_or_retry(
        self,
        to=invitation.email,
        template="invitation",
        context={
            "inviter": inviter,
            "workspace": invitation.workspace.name,
            "role": invitation.get_role_display().lower(),
            "email": invitation.email,
            "link": invitation_link(raw_token),
            "expires_on": f"{timezone.localtime(invitation.expires_at):%d %b %Y}",
        },
        idempotency_key=f"invite:{invitation.pk}",
    )
    return True
