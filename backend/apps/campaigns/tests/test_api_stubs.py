"""Campaign API contract stubs: roles, validation and the 501 envelope."""

import uuid

import pytest

from common.roles import Role
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

BASE = "/api/v1/campaigns"
DETAIL = f"{BASE}/{uuid.uuid4()}"


def campaign_body(**overrides) -> dict:
    return {
        "name": "Diwali offer",
        "template_id": str(uuid.uuid4()),
        "audience": {"tag_ids": [str(uuid.uuid4())], "match": "any"},
        "variable_mapping": {
            "body": [{"source": "contact_field", "value": "name", "fallback": "there"}],
            "header": None,
            "buttons": {"0": {"source": "static", "value": "DIWALI10"}},
        },
        **overrides,
    }


def assert_not_implemented(response):
    assert response.status_code == 501, response.content
    assert response.json()["error"]["code"] == "not_implemented"


def assert_insufficient_role(response):
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "insufficient_role"


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("get", f"{BASE}/", None),
        ("get", f"{DETAIL}/", None),
        ("get", f"{DETAIL}/recipients/", None),
        ("post", f"{DETAIL}/audience-preview/", {}),
    ],
)
def test_viewer_operations(auth_client, method, url, body):
    client = auth_client(Role.VIEWER)

    assert_not_implemented(getattr(client, method)(url, body, format="json"))


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", f"{BASE}/", campaign_body()),
        ("patch", f"{DETAIL}/", {"name": "Renamed"}),
        ("delete", f"{DETAIL}/", None),
        ("post", f"{DETAIL}/launch/", {"consent_attested": True}),
        ("post", f"{DETAIL}/pause/", {}),
        ("post", f"{DETAIL}/resume/", {}),
        ("post", f"{DETAIL}/cancel/", {}),
    ],
)
def test_writes_need_admin(auth_client, method, url, body):
    assert_insufficient_role(getattr(auth_client(Role.AGENT), method)(url, body, format="json"))
    assert_not_implemented(getattr(auth_client(Role.ADMIN), method)(url, body, format="json"))


def test_non_members_get_404(user, other_workspace):
    response = make_api_client(user, other_workspace).get(f"{BASE}/")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (campaign_body(name="  "), "name"),
        (campaign_body(template_id="nope"), "template_id"),
        (campaign_body(audience={"match": "some"}), "audience"),
        (
            campaign_body(variable_mapping={"body": [{"source": "contact_field", "value": "age"}]}),
            "variable_mapping",
        ),
        (
            campaign_body(
                variable_mapping={"buttons": {"first": {"source": "static", "value": "x"}}}
            ),
            "variable_mapping",
        ),
        ({"name": "Missing everything"}, "template_id"),
    ],
)
def test_create_validation(auth_client, body, field):
    response = auth_client(Role.ADMIN).post(f"{BASE}/", body, format="json")

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]


def test_partial_update_validates_only_sent_fields(auth_client):
    client = auth_client(Role.ADMIN)

    assert_not_implemented(client.patch(f"{DETAIL}/", {"scheduled_at": None}, format="json"))
    response = client.patch(f"{DETAIL}/", {"name": ""}, format="json")
    assert response.status_code == 400


@pytest.mark.parametrize("body", [{}, {"consent_attested": False}])
def test_launch_requires_consent_attestation(auth_client, body):
    response = auth_client(Role.ADMIN).post(f"{DETAIL}/launch/", body, format="json")

    assert response.status_code == 400
    assert "consent_attested" in response.json()["error"]["details"]


def test_unknown_campaign_id_format_is_404(auth_client):
    response = auth_client(Role.VIEWER).get(f"{BASE}/not-a-uuid/")

    assert response.status_code == 404
