"""Tenant services emit WorkspaceCreated / MembershipRoleChanged / MembershipRemoved on commit."""

import pytest
from django.urls import reverse

from apps.tenants import services
from apps.tenants.factories import MembershipFactory
from apps.tenants.models import Membership
from common import events
from common.roles import Role

pytestmark = pytest.mark.django_db


@pytest.fixture
def received():
    """Collect every tenant event sent while the test runs."""
    seen: list = []

    def collect(sender, event, **kwargs):
        seen.append(event)

    signals = (events.workspace_created, events.membership_role_changed, events.membership_removed)
    for signal in signals:
        signal.connect(collect, dispatch_uid="tenants-test-collect")
    yield seen
    for signal in signals:
        signal.disconnect(dispatch_uid="tenants-test-collect")


def owner_of(user, workspace):
    return Membership.objects.get(user=user, workspace=workspace)


def test_create_workspace_emits_after_commit(user, received, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        workspace = services.create_workspace(user=user, name="Sharma Retail")

    assert received == []
    for callback in callbacks:
        callback()

    assert received == [events.WorkspaceCreated(workspace_id=workspace.pk, owner_id=user.pk)]


def test_role_change_emits_old_and_new_role(
    user, workspace, received, django_capture_on_commit_callbacks
):
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT)

    with django_capture_on_commit_callbacks(execute=True):
        services.change_member_role(
            actor=owner_of(user, workspace), membership=agent, role=Role.ADMIN
        )
        services.change_member_role(
            actor=owner_of(user, workspace), membership=agent, role=Role.ADMIN
        )

    assert received == [
        events.MembershipRoleChanged(
            workspace_id=workspace.pk,
            user_id=agent.user_id,
            old_role=Role.AGENT,
            new_role=Role.ADMIN,
        )
    ]


def test_removal_and_leaving_emit_membership_removed(
    user, workspace, received, django_capture_on_commit_callbacks
):
    removed = MembershipFactory(workspace=workspace, role=Role.AGENT)
    leaver = MembershipFactory(workspace=workspace, role=Role.VIEWER)

    with django_capture_on_commit_callbacks(execute=True):
        services.remove_member(actor=owner_of(user, workspace), membership=removed)
        services.remove_member(actor=leaver, membership=leaver)

    assert received == [
        events.MembershipRemoved(workspace_id=workspace.pk, user_id=removed.user_id),
        events.MembershipRemoved(workspace_id=workspace.pk, user_id=leaver.user_id),
    ]
    assert not Membership.objects.filter(pk__in=[removed.pk, leaver.pk]).exists()


def test_refused_changes_emit_nothing(
    user, workspace, received, django_capture_on_commit_callbacks
):
    owner = owner_of(user, workspace)

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(services.LastOwner):
            services.change_member_role(actor=owner, membership=owner, role=Role.ADMIN)
        with pytest.raises(services.LastOwner):
            services.remove_member(actor=owner, membership=owner)

    assert received == []


def test_api_paths_emit_events(
    auth_client, workspace, received, django_capture_on_commit_callbacks
):
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT)
    url = reverse("tenants:member-detail", args=[agent.pk])
    client = auth_client()

    with django_capture_on_commit_callbacks(execute=True):
        assert client.patch(url, {"role": Role.VIEWER}).status_code == 200
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(url).status_code == 204

    assert [type(event) for event in received] == [
        events.MembershipRoleChanged,
        events.MembershipRemoved,
    ]
