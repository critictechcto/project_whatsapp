"""Automation API contract stubs: roles, validation and the 501 envelope."""

import uuid

import pytest

from common.roles import Role
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

BASE = "/api/v1/automations"
RULE = f"{BASE}/rules/{uuid.uuid4()}"


def rule_body(**overrides) -> dict:
    return {
        "name": "Price reply",
        "trigger": "keyword",
        "keywords": ["price", " PRICE "],
        "keyword_match": "contains",
        "actions": [{"type": "send_text", "config": {"text": "Our prices: ..."}}],
        **overrides,
    }


def assert_not_implemented(response):
    assert response.status_code == 501, response.content
    assert response.json()["error"]["code"] == "not_implemented"


def assert_insufficient_role(response):
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "insufficient_role"


@pytest.mark.parametrize(
    "url", [f"{BASE}/rules/", f"{RULE}/", f"{BASE}/business-hours/", f"{BASE}/runs/"]
)
def test_viewer_reads_are_stubbed(auth_client, url):
    assert_not_implemented(auth_client(Role.VIEWER).get(url))


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", f"{BASE}/rules/", rule_body()),
        ("patch", f"{RULE}/", {"is_active": False}),
        ("delete", f"{RULE}/", None),
        (
            "patch",
            f"{BASE}/business-hours/",
            {"enabled": True, "schedule": [{"day": 0, "start": "09:00", "end": "18:00"}]},
        ),
    ],
)
def test_writes_need_admin(auth_client, method, url, body):
    assert_insufficient_role(getattr(auth_client(Role.AGENT), method)(url, body, format="json"))
    assert_not_implemented(getattr(auth_client(Role.ADMIN), method)(url, body, format="json"))


def test_non_members_get_404(user, other_workspace):
    response = make_api_client(user, other_workspace).get(f"{BASE}/rules/")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (rule_body(keywords=[]), "keywords"),
        (rule_body(keywords=["  "]), "keywords"),
        ({k: v for k, v in rule_body().items() if k != "keywords"}, "keywords"),
        (rule_body(actions=[]), "actions"),
        (rule_body(actions=[{"type": "send_text", "config": {}}]), "actions"),
        (rule_body(actions=[{"type": "send_text", "config": {"text": "x"}}] * 6), "actions"),
        (rule_body(trigger="on_birthday"), "trigger"),
        (rule_body(cooldown_minutes=-1), "cooldown_minutes"),
    ],
)
def test_rule_validation(auth_client, body, field):
    response = auth_client(Role.ADMIN).post(f"{BASE}/rules/", body, format="json")

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]


def test_non_keyword_trigger_needs_no_keywords(auth_client):
    body = rule_body(
        trigger="first_inbound",
        keywords=[],
        actions=[{"type": "close_conversation", "config": {}}],
    )

    assert_not_implemented(auth_client(Role.ADMIN).post(f"{BASE}/rules/", body, format="json"))


@pytest.mark.parametrize(
    "slot",
    [
        {"day": 7, "start": "09:00", "end": "18:00"},
        {"day": 0, "start": "24:00", "end": "18:00"},
        {"day": 0, "start": "9:00", "end": "18:00"},
    ],
)
def test_business_hours_validation(auth_client, slot):
    response = auth_client(Role.ADMIN).patch(
        f"{BASE}/business-hours/", {"schedule": [slot]}, format="json"
    )

    assert response.status_code == 400, response.content
    assert "schedule" in response.json()["error"]["details"]


def test_overnight_business_hours_slot_is_allowed(auth_client):
    response = auth_client(Role.ADMIN).patch(
        f"{BASE}/business-hours/",
        {"schedule": [{"day": 4, "start": "22:00", "end": "02:00"}]},
        format="json",
    )

    assert_not_implemented(response)
