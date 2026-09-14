"""make_api_client, result_ids and assert_tenant_isolated.

This module doubles as the URLconf for its tests (``pytest.mark.urls``), so the helpers are
checked against probe endpoints that are known to be isolated or known to leak.
"""

import pytest
from django.urls import path
from rest_framework import mixins, serializers, viewsets
from rest_framework_simplejwt.tokens import AccessToken

from apps.tenants.factories import MembershipFactory
from apps.tenants.models import Membership
from common.tenancy import WorkspaceScopedGenericViewSet
from common.testing import assert_tenant_isolated, make_api_client, result_ids

pytestmark = [pytest.mark.django_db, pytest.mark.urls("common.tests.test_testing")]


class MembershipProbeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ("id", "role")


class IsolatedViewSet(
    WorkspaceScopedGenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    queryset = Membership.objects.all()
    serializer_class = MembershipProbeSerializer


class LeakyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Not workspace scoped: returns every workspace's rows."""

    queryset = Membership.objects.all()
    serializer_class = MembershipProbeSerializer


urlpatterns = [
    path("isolated/", IsolatedViewSet.as_view({"get": "list"})),
    path("isolated/<uuid:pk>/", IsolatedViewSet.as_view({"get": "retrieve"})),
    path("leaky/", LeakyViewSet.as_view({"get": "list"})),
    path("leaky/<uuid:pk>/", LeakyViewSet.as_view({"get": "retrieve"})),
]


@pytest.fixture
def foreign(other_workspace):
    return MembershipFactory(workspace=other_workspace)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_make_api_client_without_arguments_has_no_credentials(workspace):
    client = make_api_client()

    assert client._credentials == {}
    assert client.get("/isolated/").status_code == 401


def test_make_api_client_sets_jwt_and_workspace_header(user, workspace):
    client = make_api_client(user, workspace)

    authorization = client._credentials["HTTP_AUTHORIZATION"]
    assert authorization.startswith("Bearer ")
    assert str(AccessToken(authorization.removeprefix("Bearer "))["user_id"]) == str(user.pk)
    assert client._credentials["HTTP_X_WORKSPACE_ID"] == str(workspace.pk)

    response = client.get("/isolated/")
    assert response.status_code == 200
    assert str(Membership.objects.get(user=user).pk) in result_ids(response)


def test_make_api_client_user_only(user, workspace):
    client = make_api_client(user)

    assert "HTTP_X_WORKSPACE_ID" not in client._credentials
    response = client.get("/isolated/")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "workspace_required"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"results": [{"id": 1}, {"id": "b"}], "next": None}, {"1", "b"}),
        ([{"id": "a"}, {"id": 2}], {"a", "2"}),
        ([], set()),
    ],
)
def test_result_ids(data, expected):
    assert result_ids(FakeResponse(data)) == expected


def test_assert_tenant_isolated_passes_for_isolated_endpoints(user, workspace, foreign):
    client = make_api_client(user, workspace)

    assert_tenant_isolated(
        client, object_id=foreign.pk, list_url="/isolated/", detail_url=f"/isolated/{foreign.pk}/"
    )
    assert_tenant_isolated(client, object_id=foreign.pk, list_url="/isolated/")
    assert_tenant_isolated(client, object_id=foreign.pk, detail_url=f"/isolated/{foreign.pk}/")


def test_assert_tenant_isolated_fails_when_list_leaks(user, workspace, foreign):
    client = make_api_client(user, workspace)

    with pytest.raises(AssertionError):
        assert_tenant_isolated(client, object_id=foreign.pk, list_url="/leaky/")


def test_assert_tenant_isolated_fails_when_detail_leaks(user, workspace, foreign):
    client = make_api_client(user, workspace)

    with pytest.raises(AssertionError):
        assert_tenant_isolated(client, object_id=foreign.pk, detail_url=f"/leaky/{foreign.pk}/")


def test_assert_tenant_isolated_fails_when_list_errors(user, workspace, foreign):
    client = make_api_client(user)  # no workspace header: the list returns 400

    with pytest.raises(AssertionError):
        assert_tenant_isolated(client, object_id=foreign.pk, list_url="/isolated/")


def test_assert_tenant_isolated_requires_a_url(user, workspace, foreign):
    with pytest.raises(AssertionError, match="Pass list_url"):
        assert_tenant_isolated(make_api_client(user, workspace), object_id=foreign.pk)
