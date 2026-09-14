"""Test helpers shared by every app."""

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from common.tenancy import WORKSPACE_HEADER

_WORKSPACE_META_KEY = "HTTP_" + WORKSPACE_HEADER.upper().replace("-", "_")


def make_api_client(user=None, workspace=None) -> APIClient:
    """APIClient authenticated as ``user`` (JWT) and scoped to ``workspace`` via the header."""
    client = APIClient()
    credentials = {}
    if user is not None:
        credentials["HTTP_AUTHORIZATION"] = f"Bearer {AccessToken.for_user(user)}"
    if workspace is not None:
        credentials[_WORKSPACE_META_KEY] = str(workspace.pk)
    client.credentials(**credentials)
    return client


def result_ids(response) -> set[str]:
    """Ids from a list response, paginated or not."""
    data = response.json()
    items = data["results"] if isinstance(data, dict) and "results" in data else data
    return {str(item["id"]) for item in items}


def assert_tenant_isolated(client, *, object_id, list_url=None, detail_url=None) -> None:
    """``client`` acts in a different workspace than the object: it must not see it."""
    assert list_url or detail_url, "Pass list_url and/or detail_url"
    if list_url:
        response = client.get(list_url)
        assert response.status_code == 200, response.content
        assert str(object_id) not in result_ids(response)
    if detail_url:
        response = client.get(detail_url)
        assert response.status_code == 404, response.content
