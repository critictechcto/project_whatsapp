from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.tenants import tasks
from apps.tenants.factories import InvitationFactory
from apps.tenants.models import Invitation
from common import mail as mail_module
from common.mail_backends import EmailSendError
from common.roles import Role
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

INVITATIONS = reverse("tenants:invitation-list")
ACCEPT = reverse("tenants:invitation-accept")


def test_invitation_email_has_text_html_and_link(
    auth_client, user, workspace, django_capture_on_commit_callbacks
):
    user.full_name = "Ravi Sharma"
    user.save()
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client().post(INVITATIONS, {"email": "neha@example.com", "role": "admin"})
    assert response.status_code == 201, response.content

    [message] = mail.outbox
    invitation = Invitation.objects.get(email="neha@example.com")
    expires = f"{timezone.localtime(invitation.expires_at):%d %b %Y}"
    assert message.to == ["neha@example.com"]
    assert message.subject == f"Ravi Sharma invited you to {workspace.name} on UpChatz"
    assert message.extra_headers["Idempotency-Key"] == f"invite:{invitation.pk}"
    assert f"Ravi Sharma invited you to join {workspace.name} on UpChatz as admin." in message.body
    assert f"expires on {expires}" in message.body
    assert "If you weren't expecting this, you can ignore this email." in message.body
    link = message.body.split("Accept the invitation: ")[1].split()[0]
    assert link.startswith("http://testserver-frontend/app/invitations/accept?token=")
    [(html, mimetype)] = message.alternatives
    assert mimetype == "text/html"
    assert "Accept invitation" in html
    assert f'href="{link}"' in html
    assert expires in html


def test_invitation_email_skipped_when_no_longer_pending():
    revoked = InvitationFactory(revoked_at=timezone.now())
    expired = InvitationFactory(expires_at=timezone.now() - timedelta(minutes=1))

    assert tasks.send_invitation_email.delay(str(revoked.pk), "t").get() is False
    assert tasks.send_invitation_email.delay(str(expired.pk), "t").get() is False
    assert mail.outbox == []


def test_invitation_email_retries_only_retryable_failures(monkeypatch):
    invitation = InvitationFactory()
    real_send = mail_module.send_templated_email
    calls = []

    def fail_once(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise EmailSendError("Resend returned 503", retryable=True)
        real_send(**kwargs)

    monkeypatch.setattr(mail_module, "send_templated_email", fail_once)
    tasks.send_invitation_email.apply(args=[str(invitation.pk), "raw"], throw=False)

    # Retried once with the same idempotency key, then delivered.
    assert len(calls) == 2
    assert calls[0]["idempotency_key"] == calls[1]["idempotency_key"] == f"invite:{invitation.pk}"
    assert len(mail.outbox) == 1

    calls.clear()

    def fail_permanently(**kwargs):
        calls.append(kwargs)
        raise EmailSendError("Resend returned 422", retryable=False)

    monkeypatch.setattr(mail_module, "send_templated_email", fail_permanently)
    result = tasks.send_invitation_email.apply(args=[str(invitation.pk), "raw"], throw=False)
    assert isinstance(result.result, EmailSendError)
    assert len(calls) == 1


def test_accepting_an_invitation_verifies_the_email(workspace):
    invitee = UserFactory(email="asha@example.com")
    assert invitee.email_verified_at is None
    InvitationFactory(
        workspace=workspace,
        email=invitee.email,
        role=Role.AGENT,
        token_hash=Invitation.hash_token("t-ok"),
    )

    response = make_api_client(invitee).post(ACCEPT, {"token": "t-ok"})

    assert response.status_code == 200, response.content
    invitee.refresh_from_db()
    assert invitee.email_verified_at is not None


def test_accepting_keeps_an_earlier_verification_time(workspace):
    verified_at = timezone.now() - timedelta(days=10)
    invitee = UserFactory(email="asha@example.com", email_verified_at=verified_at)
    InvitationFactory(
        workspace=workspace, email=invitee.email, token_hash=Invitation.hash_token("t-ok")
    )

    assert make_api_client(invitee).post(ACCEPT, {"token": "t-ok"}).status_code == 200
    invitee.refresh_from_db()
    assert invitee.email_verified_at == verified_at
