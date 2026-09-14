"""WorkspaceScopedMixin and friends, exercised through small probe views."""

import uuid

import pytest
from rest_framework import mixins, serializers
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.factories import UserFactory
from apps.tenants.factories import MembershipFactory
from apps.tenants.models import Membership
from common.roles import Role
from common.tenancy import (
    WORKSPACE_HEADER,
    HasRole,
    WorkspaceScopedAPIView,
    WorkspaceScopedGenericViewSet,
    get_request_membership,
)

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()
HEADER_META = "HTTP_X_WORKSPACE_ID"


class ProbeView(WorkspaceScopedAPIView):
    queryset = Membership.objects.all()
    read_role = Role.AGENT
    write_role = Role.ADMIN

    def get(self, request):
        context = self.get_serializer_context()
        return Response(
            {
                "workspace": str(self.workspace.pk),
                "role": self.membership.role,
                "request_workspace": str(request.workspace.pk),
                "context_workspace": str(context["workspace"].pk),
                "context_membership": str(context["membership"].pk),
            }
        )

    def post(self, request):
        return Response({"created": True}, status=201)


class AdminOnlyView(WorkspaceScopedAPIView):
    queryset = Membership.objects.all()
    read_role = Role.VIEWER  # ignored: HasRole fixes the minimum
    permission_classes = (IsAuthenticated, HasRole(Role.ADMIN))

    def get(self, request):
        return Response({"ok": True})


class ProbeMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ("id", "user", "role")


# DRF mixins go after the scoped base so WorkspaceScopedMixin.perform_create wins in the MRO.
class ProbeViewSet(WorkspaceScopedGenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin):
    queryset = Membership.objects.all()
    serializer_class = ProbeMembershipSerializer
    pagination_class = None
    read_role = Role.AGENT
    write_role = Role.ADMIN
    action_roles = {"list": Role.ADMIN, "create": Role.AGENT, "ping": Role.VIEWER}

    def ping(self, request):
        return Response({"action": self.action})


probe_view = ProbeView.as_view()
admin_only_view = AdminOnlyView.as_view()
probe_collection = ProbeViewSet.as_view({"get": "list", "post": "create"})
probe_ping = ProbeViewSet.as_view({"get": "ping"})


def call(view, method="get", *, user=None, workspace=None, header=None, data=None):
    extra = {}
    if header is not None:
        extra[HEADER_META] = header
    elif workspace is not None:
        extra[HEADER_META] = str(workspace.pk)
    if method == "get":
        request = factory.get("/probe/", **extra)
    else:
        request = factory.post("/probe/", data or {}, format="json", **extra)
    if user is not None:
        force_authenticate(request, user=user)
    return view(request)


def member(workspace, role):
    return MembershipFactory(workspace=workspace, role=role).user


def drf_request(user, workspace=None):
    extra = {HEADER_META: str(workspace.pk)} if workspace is not None else {}
    request = Request(factory.get("/probe/", **extra))
    request.user = user
    return request


def error(response):
    return response.data["error"]


class SaveRecorder:
    def __init__(self):
        self.kwargs = None

    def save(self, **kwargs):
        self.kwargs = kwargs


def test_header_name():
    assert WORKSPACE_HEADER == "X-Workspace-ID"


@pytest.mark.parametrize("header", [None, "", "   "])
def test_missing_header_is_400(user, workspace, header):
    response = call(probe_view, user=user, header=header)

    assert response.status_code == 400
    assert error(response)["code"] == "workspace_required"
    assert WORKSPACE_HEADER in error(response)["message"]


@pytest.mark.parametrize("header", ["not-a-uuid", "1234", "' OR 1=1 --"])
def test_malformed_workspace_id_is_404(user, workspace, header):
    response = call(probe_view, user=user, header=header)

    assert response.status_code == 404
    assert error(response)["code"] == "workspace_not_found"


def test_unknown_workspace_is_404(user, workspace):
    response = call(probe_view, user=user, header=str(uuid.uuid4()))

    assert response.status_code == 404
    assert error(response)["code"] == "workspace_not_found"


def test_non_member_is_404(user, workspace, other_workspace):
    response = call(probe_view, user=user, workspace=other_workspace)

    assert response.status_code == 404
    assert error(response)["code"] == "workspace_not_found"


def test_inactive_workspace_is_404(user, workspace):
    workspace.is_active = False
    workspace.save(update_fields=["is_active"])

    response = call(probe_view, user=user, workspace=workspace)

    assert response.status_code == 404
    assert error(response)["code"] == "workspace_not_found"


@pytest.mark.parametrize("send_header", [True, False])
def test_unauthenticated_is_401(workspace, send_header):
    response = call(probe_view, workspace=workspace if send_header else None)

    assert response.status_code == 401
    assert error(response)["code"] == "not_authenticated"


@pytest.mark.parametrize(
    ("role", "status"),
    [(Role.VIEWER, 403), (Role.AGENT, 200), (Role.ADMIN, 200), (Role.OWNER, 200)],
)
def test_read_role_is_enforced(workspace, role, status):
    response = call(probe_view, user=member(workspace, role), workspace=workspace)

    assert response.status_code == status
    if status == 403:
        assert error(response)["code"] == "insufficient_role"
        assert error(response)["message"] == "This action requires the agent role or higher."


@pytest.mark.parametrize(
    ("role", "status"),
    [(Role.VIEWER, 403), (Role.AGENT, 403), (Role.ADMIN, 201), (Role.OWNER, 201)],
)
def test_write_role_is_enforced(workspace, role, status):
    response = call(probe_view, "post", user=member(workspace, role), workspace=workspace)

    assert response.status_code == status
    if status == 403:
        assert error(response)["code"] == "insufficient_role"
        assert "admin role" in error(response)["message"]


def test_view_exposes_workspace_membership_and_serializer_context(user, workspace):
    response = call(probe_view, user=user, workspace=workspace)

    membership = Membership.objects.get(user=user, workspace=workspace)
    assert response.status_code == 200
    assert response.data == {
        "workspace": str(workspace.pk),
        "role": Role.OWNER,
        "request_workspace": str(workspace.pk),
        "context_workspace": str(workspace.pk),
        "context_membership": str(membership.pk),
    }


def test_serializer_context_has_no_workspace_before_membership_resolves(user, workspace):
    view = ProbeView()
    view.request = drf_request(user, workspace)
    view.format_kwarg = None

    context = view.get_serializer_context()

    assert "workspace" not in context
    assert "membership" not in context


def test_action_roles_can_lower_the_read_role(workspace):
    viewer = member(workspace, Role.VIEWER)

    assert call(probe_ping, user=viewer, workspace=workspace).data == {"action": "ping"}
    assert call(probe_view, user=viewer, workspace=workspace).status_code == 403


def test_action_roles_can_raise_the_read_role(workspace):
    agent_response = call(probe_collection, user=member(workspace, Role.AGENT), workspace=workspace)
    admin_response = call(probe_collection, user=member(workspace, Role.ADMIN), workspace=workspace)

    assert agent_response.status_code == 403
    assert error(agent_response)["code"] == "insufficient_role"
    assert admin_response.status_code == 200


def test_action_roles_can_lower_the_write_role(workspace):
    new_user = UserFactory()
    data = {"user": str(new_user.pk), "role": Role.VIEWER}

    viewer_response = call(
        probe_collection,
        "post",
        user=member(workspace, Role.VIEWER),
        workspace=workspace,
        data=data,
    )
    agent_response = call(
        probe_collection, "post", user=member(workspace, Role.AGENT), workspace=workspace, data=data
    )

    assert viewer_response.status_code == 403
    assert agent_response.status_code == 201, agent_response.data


@pytest.mark.parametrize(
    ("role", "status"),
    [(Role.VIEWER, 403), (Role.AGENT, 403), (Role.ADMIN, 200), (Role.OWNER, 200)],
)
def test_has_role_fixes_the_minimum(workspace, role, status):
    response = call(admin_only_view, user=member(workspace, role), workspace=workspace)

    assert response.status_code == status
    if status == 403:
        assert error(response)["code"] == "insufficient_role"
        assert "admin role" in error(response)["message"]


def test_has_role_class_name():
    assert HasRole(Role.ADMIN).__name__ == "HasRoleAdmin"
    assert HasRole(Role.VIEWER).__name__ == "HasRoleViewer"


def test_has_role_still_requires_membership(user, workspace, other_workspace):
    response = call(admin_only_view, user=user, workspace=other_workspace)

    assert response.status_code == 404


def test_queryset_is_filtered_to_workspace(workspace, other_workspace):
    admin = member(workspace, Role.ADMIN)
    MembershipFactory.create_batch(2, workspace=workspace)
    MembershipFactory.create_batch(2, workspace=other_workspace)

    response = call(probe_collection, user=admin, workspace=workspace)

    assert response.status_code == 200
    expected = {str(pk) for pk in workspace.memberships.values_list("pk", flat=True)}
    assert {item["id"] for item in response.data} == expected
    assert len(expected) == 4  # owner, admin and two more


def test_queryset_is_empty_for_schema_generation():
    view = ProbeView()
    view.swagger_fake_view = True
    view.request = Request(factory.get("/probe/"))

    assert view.get_queryset().query.is_empty()


def test_perform_create_sets_workspace(workspace, other_workspace):
    new_user = UserFactory()
    response = call(
        probe_collection,
        "post",
        user=member(workspace, Role.AGENT),
        workspace=workspace,
        data={"user": str(new_user.pk), "role": Role.VIEWER},
    )

    assert response.status_code == 201, response.data
    created = Membership.objects.get(pk=response.data["id"])
    assert created.workspace == workspace
    assert created.user == new_user


def test_perform_create_passes_workspace_to_save(user, workspace):
    view = ProbeViewSet()
    view.request = drf_request(user, workspace)
    serializer = SaveRecorder()

    view.perform_create(serializer)

    assert serializer.kwargs == {"workspace": workspace}


def test_perform_create_with_nested_workspace_field_does_not_set_it(user, workspace):
    view = ProbeViewSet()
    view.request = drf_request(user, workspace)
    view.workspace_field = "user__memberships__workspace"
    serializer = SaveRecorder()

    view.perform_create(serializer)

    assert serializer.kwargs == {}


def test_get_request_membership_is_cached(user, workspace, django_assert_num_queries):
    request = drf_request(user, workspace)

    with django_assert_num_queries(1):
        first = get_request_membership(request)
        second = get_request_membership(request)

    assert first is second
    assert request.membership is first
    assert request.workspace == workspace


def test_get_request_membership_requires_authentication(workspace):
    request = Request(factory.get("/probe/", **{HEADER_META: str(workspace.pk)}))

    with pytest.raises(NotAuthenticated):
        get_request_membership(request)


def test_create_mixin_listed_before_workspace_mixin_is_rejected():
    from django.core.exceptions import ImproperlyConfigured

    from common.tenancy import WorkspaceScopedGenericViewSet

    with pytest.raises(ImproperlyConfigured):
        type("BadViewSet", (mixins.CreateModelMixin, WorkspaceScopedGenericViewSet), {})
    type("GoodViewSet", (WorkspaceScopedGenericViewSet, mixins.CreateModelMixin), {})
