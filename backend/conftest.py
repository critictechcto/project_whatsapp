import pytest

from apps.accounts.factories import UserFactory
from apps.payments.testing import fake_payments  # noqa: F401  (fixture for every app's tests)
from apps.tenants.factories import MembershipFactory, WorkspaceFactory
from apps.tenants.models import Membership
from apps.whatsapp.client import override_client
from apps.whatsapp.client.fake import FakeGraphClient
from common.roles import Role
from common.testing import make_api_client


@pytest.fixture
def api_client():
    """Unauthenticated client."""
    return make_api_client()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def workspace(db, user):
    """Workspace owned by ``user``."""
    workspace = WorkspaceFactory(created_by=user)
    MembershipFactory(workspace=workspace, user=user, role=Role.OWNER)
    return workspace


@pytest.fixture
def other_workspace(db):
    """A workspace ``user`` does not belong to."""
    workspace = WorkspaceFactory()
    MembershipFactory(workspace=workspace, role=Role.OWNER)
    return workspace


@pytest.fixture
def auth_client(db, user, workspace):
    """Factory for JWT clients scoped to a workspace via X-Workspace-ID.

    - ``auth_client()`` → the ``user`` fixture, owner of ``workspace``
    - ``auth_client(Role.AGENT)`` → a new member of ``workspace`` with that role
    - ``auth_client(workspace=other_workspace)`` → a new owner of another workspace
    - ``auth_client(Role.ADMIN, user=some_user)`` → that user, given that role
    """
    default_user, default_workspace = user, workspace

    def make(role: str = Role.OWNER, *, user=None, workspace=None):
        workspace = workspace or default_workspace
        if user is None:
            is_default_owner = role == Role.OWNER and workspace == default_workspace
            user = default_user if is_default_owner else UserFactory()
        Membership.objects.update_or_create(workspace=workspace, user=user, defaults={"role": role})
        return make_api_client(user, workspace)

    return make


@pytest.fixture
def fake_graph():
    """Shared FakeGraphClient returned by every get_client() call during the test."""
    fake = FakeGraphClient()
    with override_client(fake):
        yield fake
