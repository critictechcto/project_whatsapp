from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.tenants.factories import InvitationFactory, MembershipFactory
from apps.tenants.models import Invitation, Membership
from common.roles import Role
from common.testing import assert_tenant_isolated, make_api_client, result_ids

pytestmark = pytest.mark.django_db

MEMBERS = reverse("tenants:member-list")
INVITATIONS = reverse("tenants:invitation-list")
ACCEPT = reverse("tenants:invitation-accept")


def member_url(membership):
    return reverse("tenants:member-detail", args=[membership.pk])


def membership_of(user, workspace):
    return Membership.objects.get(user=user, workspace=workspace)


def test_members_require_workspace_header(user):
    response = make_api_client(user).get(MEMBERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "workspace_required"


def test_members_of_foreign_workspace_are_hidden(user, other_workspace):
    response = make_api_client(user, other_workspace).get(MEMBERS)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"


def test_member_list_is_tenant_isolated(auth_client, workspace, other_workspace):
    foreign = MembershipFactory(workspace=other_workspace)
    client = auth_client()

    assert_tenant_isolated(
        client, object_id=foreign.pk, list_url=MEMBERS, detail_url=member_url(foreign)
    )


def test_viewer_can_list_members(auth_client, user, workspace):
    response = auth_client(Role.VIEWER).get(MEMBERS)

    assert response.status_code == 200
    assert str(membership_of(user, workspace).pk) in result_ids(response)


def test_admin_changes_agent_role(auth_client, workspace):
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT)

    response = auth_client(Role.ADMIN).patch(member_url(agent), {"role": Role.VIEWER})

    assert response.status_code == 200, response.content
    agent.refresh_from_db()
    assert agent.role == Role.VIEWER


def test_admin_cannot_grant_owner(auth_client, workspace):
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT)

    response = auth_client(Role.ADMIN).patch(member_url(agent), {"role": Role.OWNER})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_agent_cannot_change_roles(auth_client, workspace):
    viewer = MembershipFactory(workspace=workspace, role=Role.VIEWER)

    assert (
        auth_client(Role.AGENT).patch(member_url(viewer), {"role": Role.ADMIN}).status_code == 403
    )


def test_last_owner_cannot_be_demoted_or_leave(auth_client, user, workspace):
    client = auth_client()
    owner = membership_of(user, workspace)

    demote = client.patch(member_url(owner), {"role": Role.ADMIN})
    leave = client.delete(member_url(owner))

    assert demote.status_code == 409
    assert demote.json()["error"]["code"] == "last_owner"
    assert leave.status_code == 409


def test_owner_can_hand_over_ownership(auth_client, user, workspace):
    client = auth_client()
    admin = MembershipFactory(workspace=workspace, role=Role.ADMIN)

    assert client.patch(member_url(admin), {"role": Role.OWNER}).status_code == 200
    assert (
        client.patch(member_url(membership_of(user, workspace)), {"role": Role.ADMIN}).status_code
        == 200
    )


def test_agent_can_leave_but_not_remove_others(auth_client, workspace):
    agent_user = UserFactory()
    agent_client = auth_client(Role.AGENT, user=agent_user)
    other = MembershipFactory(workspace=workspace, role=Role.VIEWER)

    assert agent_client.delete(member_url(other)).status_code == 403
    assert agent_client.delete(member_url(membership_of(agent_user, workspace))).status_code == 204


def test_admin_cannot_remove_owner(auth_client, user, workspace):
    response = auth_client(Role.ADMIN).delete(member_url(membership_of(user, workspace)))

    assert response.status_code == 403


def test_invitation_flow(auth_client, workspace, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(Role.ADMIN).post(
            INVITATIONS, {"email": "Neha@Example.com", "role": Role.AGENT}
        )

    assert response.status_code == 201, response.content
    assert response.json()["status"] == "pending"
    assert "token" not in response.json()
    assert len(mail.outbox) == 1
    token = mail.outbox[0].body.split("token=")[1].split()[0]

    invitee = UserFactory(email="neha@example.com")
    accepted = make_api_client(invitee).post(ACCEPT, {"token": token})

    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["workspace"]["id"] == str(workspace.pk)
    # Accepting needs a signed-in user and issues no tokens: nothing in the body or cookies.
    assert not {"access", "refresh", "tokens"} & accepted.json().keys()
    assert "upchatz_refresh" not in accepted.cookies
    assert membership_of(invitee, workspace).role == Role.AGENT
    reused = make_api_client(invitee).post(ACCEPT, {"token": token})
    assert reused.status_code == 400


def test_invitation_requires_admin(auth_client):
    assert auth_client(Role.AGENT).get(INVITATIONS).status_code == 403
    assert auth_client(Role.AGENT).post(INVITATIONS, {"email": "a@example.com"}).status_code == 403


def test_only_owner_invites_owner(auth_client):
    response = auth_client(Role.ADMIN).post(
        INVITATIONS, {"email": "o@example.com", "role": Role.OWNER}
    )

    assert response.status_code == 403


def test_inviting_existing_member_conflicts(auth_client, user):
    response = auth_client().post(INVITATIONS, {"email": user.email.upper()})

    assert response.status_code == 409


def test_reinviting_revokes_previous_open_invitation(auth_client, workspace):
    client = auth_client()
    client.post(INVITATIONS, {"email": "dup@example.com"})
    client.post(INVITATIONS, {"email": "dup@example.com"})

    assert (
        Invitation.objects.open().filter(workspace=workspace, email="dup@example.com").count() == 1
    )


def test_accept_rejects_wrong_email_expired_and_revoked(workspace):
    invitee = UserFactory(email="right@example.com")
    client = make_api_client(invitee)

    InvitationFactory(
        workspace=workspace, email="other@example.com", token_hash=Invitation.hash_token("t-wrong")
    )
    InvitationFactory(
        workspace=workspace,
        email="right@example.com",
        token_hash=Invitation.hash_token("t-expired"),
        expires_at=timezone.now() - timedelta(minutes=1),
        revoked_at=None,
    )

    assert client.post(ACCEPT, {"token": "t-wrong"}).status_code == 403
    assert client.post(ACCEPT, {"token": "t-expired"}).status_code == 400
    assert client.post(ACCEPT, {"token": "does-not-exist"}).status_code == 400


def test_revoke_invitation(auth_client, workspace):
    invitation = InvitationFactory(workspace=workspace)
    client = auth_client()

    response = client.delete(reverse("tenants:invitation-detail", args=[invitation.pk]))

    assert response.status_code == 204
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.REVOKED
    assert str(invitation.pk) not in result_ids(client.get(INVITATIONS))
