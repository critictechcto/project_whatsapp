import pytest
from django.urls import reverse

from apps.tenants.factories import MembershipFactory, WorkspaceFactory
from apps.tenants.models import Membership, Workspace
from common.roles import Role
from common.testing import make_api_client, result_ids

pytestmark = pytest.mark.django_db

LIST = reverse("tenants:workspace-list")


def detail(workspace):
    return reverse("tenants:workspace-detail", args=[workspace.pk])


def test_create_workspace_makes_caller_owner(user):
    client = make_api_client(user)

    first = client.post(LIST, {"name": "Sharma Retail"})
    second = client.post(LIST, {"name": "Sharma Retail"})

    assert first.status_code == 201, first.content
    assert first.json()["my_role"] == "owner"
    assert first.json()["time_zone"] == "Asia/Kolkata"
    assert first.json()["slug"] != second.json()["slug"]
    membership = Membership.objects.get(workspace_id=first.json()["id"], user=user)
    assert membership.role == Role.OWNER


def test_create_workspace_rejects_unknown_time_zone(user):
    response = make_api_client(user).post(LIST, {"name": "X", "time_zone": "Mars/Olympus"})

    assert response.status_code == 400


def test_list_shows_only_my_active_workspaces(user, workspace):
    WorkspaceFactory()  # someone else's
    inactive = WorkspaceFactory(is_active=False)
    MembershipFactory(workspace=inactive, user=user, role=Role.OWNER)

    response = make_api_client(user).get(LIST)

    assert response.status_code == 200
    assert result_ids(response) == {str(workspace.pk)}


def test_cannot_retrieve_workspace_i_do_not_belong_to(user):
    other = WorkspaceFactory()

    assert make_api_client(user).get(detail(other)).status_code == 404


@pytest.mark.parametrize(("role", "expected"), [(Role.AGENT, 403), (Role.ADMIN, 200)])
def test_update_requires_admin(auth_client, workspace, role, expected):
    client = auth_client(role)

    response = client.patch(detail(workspace), {"name": "Renamed"})

    assert response.status_code == expected, response.content


@pytest.mark.parametrize(("role", "expected"), [(Role.ADMIN, 403), (Role.OWNER, 204)])
def test_delete_requires_owner_and_soft_deletes(auth_client, workspace, role, expected):
    client = auth_client(role)

    response = client.delete(detail(workspace))

    assert response.status_code == expected
    workspace.refresh_from_db()
    assert workspace.is_active is (expected != 204)
    assert Workspace.objects.filter(pk=workspace.pk).exists()
