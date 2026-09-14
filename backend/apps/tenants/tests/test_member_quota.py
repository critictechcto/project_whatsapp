"""Member quota: invitations reserve a seat (members + open, unexpired invitations) and
accepting re-checks the limit."""

from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.billing import entitlements
from apps.billing import services as billing_services
from apps.billing.models import Subscription
from apps.tenants.factories import InvitationFactory, MembershipFactory
from apps.tenants.models import Invitation, Membership
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

INVITATIONS = reverse("tenants:invitation-list")
ACCEPT = reverse("tenants:invitation-accept")
STARTER_MEMBERS = 2


def use_plan(workspace, plan: str) -> None:
    subscription = billing_services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(plan_id=plan)
    entitlements.clear_cache(workspace)


def quota_error(response) -> dict:
    assert response.status_code == 409, response.content
    error = response.json()["error"]
    assert error["code"] == "quota_exceeded"
    return error


def invite(client, email: str):
    return client.post(INVITATIONS, {"email": email, "role": "agent"})


def test_pending_invitations_count_toward_the_member_limit(auth_client, workspace):
    use_plan(workspace, "starter")  # 2 members; the owner is one
    client = auth_client()

    first = invite(client, "asha@example.com")
    second = invite(client, "ravi@example.com")

    assert first.status_code == 201, first.content
    error = quota_error(second)
    assert error["details"] == {"metric": "members", "limit": STARTER_MEMBERS, "used": 1}
    assert "1 pending invitation counts toward the limit" in error["message"]
    assert not Invitation.objects.filter(email="ravi@example.com").exists()


def test_reinviting_the_same_email_does_not_use_another_seat(auth_client, workspace):
    use_plan(workspace, "starter")
    client = auth_client()

    assert invite(client, "asha@example.com").status_code == 201
    again = invite(client, "ASHA@example.com")

    assert again.status_code == 201, again.content
    assert Invitation.objects.open().filter(workspace=workspace).count() == 1


def test_revoked_and_expired_invitations_free_their_seat(auth_client, workspace):
    use_plan(workspace, "starter")
    client = auth_client()
    InvitationFactory(workspace=workspace, email="old@example.com", revoked_at=timezone.now())
    InvitationFactory(
        workspace=workspace,
        email="late@example.com",
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    response = invite(client, "asha@example.com")

    assert response.status_code == 201, response.content


def test_full_workspace_cannot_invite(auth_client, workspace):
    use_plan(workspace, "starter")
    MembershipFactory(workspace=workspace)

    error = quota_error(invite(auth_client(), "asha@example.com"))

    assert error["details"] == {"metric": "members", "limit": STARTER_MEMBERS, "used": 2}
    assert "pending" not in error["message"]


def test_restricted_subscription_cannot_invite(auth_client, workspace):
    subscription = billing_services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(status="expired")
    entitlements.clear_cache(workspace)

    error = quota_error(invite(auth_client(), "asha@example.com"))

    assert error["details"]["metric"] == "members"


def test_accept_rechecks_the_limit(auth_client, workspace, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        assert invite(auth_client(), "asha@example.com").status_code == 201
    token = mail.outbox[-1].body.split("token=")[1].split()[0]
    # The workspace filled up (and moved to a smaller plan) after the invitation was sent.
    use_plan(workspace, "starter")
    MembershipFactory(workspace=workspace)
    invitee = UserFactory(email="asha@example.com")

    error = quota_error(make_api_client(invitee).post(ACCEPT, {"token": token}))

    assert error["details"] == {"metric": "members", "limit": STARTER_MEMBERS, "used": 2}
    assert not Membership.objects.filter(workspace=workspace, user=invitee).exists()
    invitation = Invitation.objects.get(workspace=workspace, email="asha@example.com")
    assert invitation.status == Invitation.Status.PENDING


def test_accept_within_the_limit_joins(workspace):
    use_plan(workspace, "starter")
    invitee = UserFactory(email="asha@example.com")
    InvitationFactory(
        workspace=workspace, email=invitee.email, token_hash=Invitation.hash_token("t-ok")
    )

    response = make_api_client(invitee).post(ACCEPT, {"token": "t-ok"})

    assert response.status_code == 200, response.content
    assert Membership.objects.filter(workspace=workspace, user=invitee).exists()
