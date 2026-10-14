import importlib

import pytest
from django.apps import apps as django_apps
from django.urls import reverse

from apps.tenants.factories import MembershipFactory
from apps.tenants.models import Membership
from common.roles import Role
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

ONBOARDING = reverse("tenants:onboarding")


def test_new_member_starts_with_nothing_done(auth_client):
    response = auth_client().get(ONBOARDING)

    assert response.status_code == 200
    assert response.json() == {
        "goals": [],
        "welcome_completed": False,
        "tour_completed": False,
        "checklist_dismissed": False,
        "can_set_goal": True,
    }


def test_flags_are_per_person_and_can_be_cleared(auth_client, user, workspace):
    owner = auth_client()
    agent = auth_client(Role.AGENT)

    response = owner.patch(
        ONBOARDING, {"welcome_completed": True, "tour_completed": True}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["welcome_completed"] is True
    assert response.json()["tour_completed"] is True
    stamped = Membership.objects.get(user=user, workspace=workspace).welcome_completed_at
    assert stamped is not None

    # Setting a flag again keeps the first time; false clears it (replay the tour).
    owner.patch(ONBOARDING, {"welcome_completed": True}, format="json")
    assert Membership.objects.get(user=user, workspace=workspace).welcome_completed_at == stamped
    response = owner.patch(ONBOARDING, {"tour_completed": False}, format="json")
    assert response.json()["tour_completed"] is False

    assert agent.get(ONBOARDING).json()["welcome_completed"] is False


def test_admin_sets_the_workspace_goals_for_everyone(auth_client, workspace):
    admin = auth_client(Role.ADMIN)
    response = admin.patch(ONBOARDING, {"goals": ["support", "sell", "sell"]}, format="json")

    assert response.status_code == 200
    assert response.json()["goals"] == ["sell", "support"]
    workspace.refresh_from_db()
    assert workspace.business_goals == ["sell", "support"]
    viewer = auth_client(Role.VIEWER).get(ONBOARDING).json()
    assert viewer["goals"] == ["sell", "support"]
    assert viewer["can_set_goal"] is False


@pytest.mark.parametrize("role", [Role.AGENT, Role.VIEWER])
def test_members_below_admin_cannot_set_the_goal(auth_client, workspace, role):
    client = auth_client(role)

    response = client.patch(
        ONBOARDING, {"goals": ["marketing"], "welcome_completed": True}, format="json"
    )

    assert response.status_code == 403
    workspace.refresh_from_db()
    assert workspace.business_goals == []
    # Their own flags still work on their own.
    assert client.patch(ONBOARDING, {"welcome_completed": True}, format="json").status_code == 200


def test_goals_can_be_cleared(auth_client):
    client = auth_client()
    client.patch(ONBOARDING, {"goals": ["sell"]}, format="json")

    response = client.patch(ONBOARDING, {"goals": []}, format="json")

    assert response.json()["goals"] == []


def test_invalid_goal_is_rejected(auth_client):
    response = auth_client().patch(ONBOARDING, {"goals": ["everything"]}, format="json")

    assert response.status_code == 400
    assert "goals" in response.json()["error"]["details"]


def test_non_member_gets_404(user, other_workspace):
    client = make_api_client(user, other_workspace)

    assert client.get(ONBOARDING).status_code == 404
    assert client.patch(ONBOARDING, {"welcome_completed": True}, format="json").status_code == 404


def test_requires_workspace_header(user):
    response = make_api_client(user).get(ONBOARDING)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "workspace_required"


def test_data_migration_marks_existing_members_welcomed(workspace):
    membership = MembershipFactory(workspace=workspace, role=Role.AGENT)
    migration = importlib.import_module("apps.tenants.migrations.0002_onboarding")

    migration.mark_existing_members_welcomed(django_apps, None)

    membership.refresh_from_db()
    assert membership.welcome_completed_at is not None
