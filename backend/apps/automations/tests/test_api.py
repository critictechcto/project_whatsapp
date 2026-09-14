"""Automation API: rules CRUD and validation, the plan gate, business hours, runs, roles and
tenant isolation."""

import uuid
from datetime import timedelta
from unittest.mock import ANY

import pytest
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.automations.factories import (
    AutomationRuleFactory,
    AutomationRunFactory,
    BusinessHoursFactory,
)
from apps.automations.models import AutomationRule, AutomationRun, BusinessHours
from apps.billing import entitlements
from apps.contacts.factories import TagFactory
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.tenants.factories import MembershipFactory
from apps.whatsapp.factories import PhoneNumberFactory
from common.roles import Role
from common.testing import assert_tenant_isolated, make_api_client, result_ids

pytestmark = pytest.mark.django_db

BASE = "/api/v1/automations"
RULES = f"{BASE}/rules/"
HOURS = f"{BASE}/business-hours/"
RUNS = f"{BASE}/runs/"


def rule_url(rule) -> str:
    return f"{RULES}{rule.pk if hasattr(rule, 'pk') else rule}/"


def rule_body(**overrides) -> dict:
    return {
        "name": "Price reply",
        "trigger": "keyword",
        "keywords": ["price", " PRICE "],
        "keyword_match": "contains",
        "actions": [{"type": "send_text", "config": {"text": "Our prices: ..."}}],
        **overrides,
    }


def template_action(template, body_params=None) -> dict:
    return {
        "type": "send_template",
        "config": {"template_id": str(template.pk), "body_params": body_params or []},
    }


def assert_invalid(response, *path):
    assert response.status_code == 400, response.content
    details = response.json()["error"]["details"]
    for key in path:
        # DRF reports list items by index; JSON turns those keys into strings.
        details = details[str(key)] if isinstance(details, dict) else details[key]
    assert details
    return details


@pytest.fixture
def admin(auth_client):
    return auth_client(Role.ADMIN)


@pytest.fixture
def no_keyword_feature(monkeypatch):
    real = entitlements.has_feature

    def has_feature(workspace, feature):
        return feature != entitlements.KEYWORD_AUTOMATIONS and real(workspace, feature)

    monkeypatch.setattr(entitlements, "has_feature", has_feature)


# --- Roles and isolation ------------------------------------------------------------------------


@pytest.mark.parametrize("url", [RULES, HOURS, RUNS])
def test_viewers_can_read(auth_client, url):
    assert auth_client(Role.VIEWER).get(url).status_code == 200


def test_viewer_can_retrieve_a_rule(auth_client, workspace):
    rule = AutomationRuleFactory(workspace=workspace)

    response = auth_client(Role.VIEWER).get(rule_url(rule))

    assert response.status_code == 200
    assert response.json()["id"] == str(rule.pk)


@pytest.mark.parametrize(
    ("method", "target", "body"),
    [
        ("post", RULES, rule_body()),
        ("patch", "rule", {"is_active": False}),
        ("delete", "rule", None),
        (
            "patch",
            HOURS,
            {"enabled": True, "schedule": [{"day": 0, "start": "09:00", "end": "18:00"}]},
        ),
    ],
)
def test_writes_need_admin(auth_client, workspace, method, target, body):
    rule = AutomationRuleFactory(workspace=workspace)
    url = rule_url(rule) if target == "rule" else target

    response = getattr(auth_client(Role.AGENT), method)(url, body, format="json")
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "insufficient_role"

    response = getattr(auth_client(Role.ADMIN), method)(url, body, format="json")
    assert response.status_code in (200, 201, 204), response.content


def test_non_members_get_404(user, other_workspace):
    response = make_api_client(user, other_workspace).get(RULES)

    assert response.status_code == 404


def test_rules_and_runs_are_tenant_isolated(auth_client, other_workspace):
    rule = AutomationRuleFactory(workspace=other_workspace)
    run = AutomationRunFactory(message__conversation__workspace=other_workspace)
    client = auth_client()

    assert_tenant_isolated(client, object_id=rule.pk, list_url=RULES, detail_url=rule_url(rule))
    assert_tenant_isolated(client, object_id=run.pk, list_url=RUNS)
    assert client.patch(rule_url(rule), {"name": "Mine now"}, format="json").status_code == 404
    assert client.delete(rule_url(rule)).status_code == 404
    assert AutomationRule.objects.filter(pk=rule.pk, name=rule.name).exists()


# --- Rules --------------------------------------------------------------------------------------


def test_create_keyword_rule_normalises_keywords(admin, workspace):
    response = admin.post(
        RULES, rule_body(keywords=["Price", " PRICE ", "Rate  Card"]), format="json"
    )

    assert response.status_code == 201, response.content
    data = response.json()
    assert data == {
        "id": ANY,
        "name": "Price reply",
        "is_active": True,
        "trigger": "keyword",
        "keywords": ["price", "rate card"],
        "keyword_match": "contains",
        "phone_number_id": None,
        "actions": [{"type": "send_text", "config": {"text": "Our prices: ..."}}],
        "cooldown_minutes": 0,
        "priority": 0,
        "stop_processing": False,
        "run_count": 0,
        "last_triggered_at": None,
        "created_at": ANY,
        "updated_at": ANY,
    }
    rule = AutomationRule.objects.get(pk=data["id"])
    assert rule.workspace == workspace
    assert rule.keywords == ["price", "rate card"]


def test_create_rule_with_every_action_type(admin, workspace, number):
    template = MessageTemplateFactory(waba=number.waba, status=MessageTemplate.Status.APPROVED)
    tag = TagFactory(workspace=workspace)
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT).user
    body = rule_body(
        trigger="first_inbound",
        keywords=[],
        phone_number_id=str(number.pk),
        actions=[
            {"type": "send_text", "config": {"text": "  Welcome!  ", "extra": 1}},
            template_action(
                template,
                [
                    {"source": "contact_field", "value": "name", "fallback": "there"},
                    {"source": "attribute", "value": " order_id "},
                ],
            ),
            {"type": "add_tags", "config": {"tag_ids": [str(tag.pk), str(tag.pk)]}},
            {"type": "assign", "config": {"user_id": str(agent.pk)}},
            {"type": "close_conversation", "config": {"ignored": True}},
        ],
    )

    response = admin.post(RULES, body, format="json")

    assert response.status_code == 201, response.content
    assert response.json()["phone_number_id"] == str(number.pk)
    assert response.json()["actions"] == [
        {"type": "send_text", "config": {"text": "Welcome!"}},
        {
            "type": "send_template",
            "config": {
                "template_id": str(template.pk),
                "body_params": [
                    {"source": "contact_field", "value": "name", "fallback": "there"},
                    {"source": "attribute", "value": "order_id", "fallback": ""},
                ],
            },
        },
        {"type": "add_tags", "config": {"tag_ids": [str(tag.pk)]}},
        {"type": "assign", "config": {"user_id": str(agent.pk)}},
        {"type": "close_conversation", "config": {}},
    ]
    assert AutomationRule.objects.get().actions == response.json()["actions"]


def test_create_rule_with_commerce_actions(admin):
    collection_id = uuid.uuid4()
    body = rule_body(
        trigger="first_inbound",
        keywords=[],
        actions=[
            {"type": "send_shop_menu", "config": {"ignored": True}},
            {"type": "send_catalog"},
            {"type": "send_collection", "config": {"collection_id": str(collection_id).upper()}},
        ],
    )

    response = admin.post(RULES, body, format="json")

    assert response.status_code == 201, response.content
    assert response.json()["actions"] == [
        {"type": "send_shop_menu", "config": {}},
        {"type": "send_catalog", "config": {}},
        {"type": "send_collection", "config": {"collection_id": str(collection_id)}},
    ]


@pytest.mark.parametrize("config", [{}, {"collection_id": "summer"}, {"collection_id": None}])
def test_send_collection_needs_a_collection_id(admin, config):
    body = rule_body(
        trigger="first_inbound",
        keywords=[],
        actions=[{"type": "send_collection", "config": config}],
    )

    response = admin.post(RULES, body, format="json")

    assert_invalid(response, "actions", 0, "config")
    assert not AutomationRule.objects.exists()


def test_non_keyword_trigger_needs_no_keywords(admin):
    body = rule_body(
        trigger="first_inbound",
        keywords=[],
        actions=[{"type": "close_conversation", "config": {}}],
    )

    assert admin.post(RULES, body, format="json").status_code == 201


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (rule_body(keywords=[]), "keywords"),
        (rule_body(keywords=["  "]), "keywords"),
        ({k: v for k, v in rule_body().items() if k != "keywords"}, "keywords"),
        (rule_body(actions=[]), "actions"),
        (rule_body(actions=[{"type": "send_text", "config": {}}]), "actions"),
        (rule_body(actions=[{"type": "send_text", "config": {"text": "x"}}] * 6), "actions"),
        (rule_body(actions=[{"type": "send_text", "config": {"text": "   "}}]), "actions"),
        (rule_body(actions=[{"type": "send_text", "config": {"text": "x" * 4097}}]), "actions"),
        (rule_body(actions=[{"type": "reboot", "config": {}}]), "actions"),
        (rule_body(trigger="on_birthday"), "trigger"),
        (rule_body(keyword_match="regex"), "keyword_match"),
        (rule_body(cooldown_minutes=-1), "cooldown_minutes"),
        (rule_body(phone_number_id="not-a-uuid"), "phone_number_id"),
    ],
)
def test_rule_validation(admin, body, field):
    assert_invalid(admin.post(RULES, body, format="json"), field)
    assert not AutomationRule.objects.exists()


def test_phone_number_must_belong_to_the_workspace(admin, other_workspace):
    foreign = PhoneNumberFactory(workspace=other_workspace, waba__workspace=other_workspace)

    response = admin.post(RULES, rule_body(phone_number_id=str(foreign.pk)), format="json")

    assert_invalid(response, "phone_number_id")


def test_send_template_validation(admin, workspace, number, other_workspace):
    approved = MessageTemplateFactory(waba=number.waba, status=MessageTemplate.Status.APPROVED)
    two_params = [
        {"source": "contact_field", "value": "name"},
        {"source": "static", "value": "42"},
    ]
    foreign = MessageTemplateFactory(
        waba__workspace=other_workspace, status=MessageTemplate.Status.APPROVED
    )
    header_variable = MessageTemplateFactory(
        waba=number.waba,
        status=MessageTemplate.Status.APPROVED,
        components=[
            {
                "type": "HEADER",
                "format": "TEXT",
                "text": "Order {{1}}",
                "example": {"header_text": ["42"]},
            },
            {"type": "BODY", "text": "Your order is ready."},
        ],
    )

    def post(action, **overrides):
        return admin.post(RULES, rule_body(actions=[action], **overrides), format="json")

    config = ("actions", 0, "config")
    assert_invalid(post(template_action(foreign, two_params)), *config, "template_id")
    bad_id = {"type": "send_template", "config": {"template_id": "nope", "body_params": []}}
    assert_invalid(post(bad_id), *config, "template_id")
    assert (
        "2 variable(s) but 1"
        in assert_invalid(post(template_action(approved, two_params[:1])), *config, "body_params")[
            0
        ]
    )
    unknown_field = [{"source": "contact_field", "value": "age"}, two_params[1]]
    assert_invalid(post(template_action(approved, unknown_field)), *config, "body_params")
    bad_source = [{"source": "sql", "value": "x"}, two_params[1]]
    assert_invalid(post(template_action(approved, bad_source)), *config, "body_params")
    no_list = {
        "type": "send_template",
        "config": {"template_id": str(approved.pk), "body_params": "x"},
    }
    assert_invalid(post(no_list), *config, "body_params")
    assert_invalid(post(template_action(header_variable)), *config, "template_id")

    other_number = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)
    mismatch = post(template_action(approved, two_params), phone_number_id=str(other_number.pk))
    assert (
        "different WhatsApp Business Account" in assert_invalid(mismatch, *config, "template_id")[0]
    )

    assert post(template_action(approved, two_params)).status_code == 201
    draft = MessageTemplateFactory(waba=number.waba)  # validated now, approval checked at send
    assert post(template_action(draft, two_params)).status_code == 201


def test_add_tags_and_assign_validation(admin, workspace, other_workspace):
    foreign_tag = TagFactory(workspace=other_workspace)
    tag = TagFactory(workspace=workspace)
    outsider = UserFactory()
    config = ("actions", 0, "config")

    def post(action):
        return admin.post(RULES, rule_body(actions=[action]), format="json")

    for tag_ids in ([], [str(tag.pk), str(foreign_tag.pk)], ["nope"], "x"):
        response = post({"type": "add_tags", "config": {"tag_ids": tag_ids}})
        assert_invalid(response, *config, "tag_ids")
    for user_id in (str(outsider.pk), "nope", None):
        assert_invalid(post({"type": "assign", "config": {"user_id": user_id}}), *config, "user_id")
    assert not AutomationRule.objects.exists()


def test_partial_update_and_delete(admin, workspace):
    rule = AutomationRuleFactory(workspace=workspace, priority=5)
    actions = rule.actions

    response = admin.patch(
        rule_url(rule),
        {"priority": 1, "stop_processing": True, "keywords": ["  Hello  THERE "]},
        format="json",
    )

    assert response.status_code == 200, response.content
    data = response.json()
    assert (data["priority"], data["stop_processing"], data["keywords"]) == (
        1,
        True,
        ["hello there"],
    )
    assert data["actions"] == actions
    rule.refresh_from_db()
    assert (rule.priority, rule.keywords) == (1, ["hello there"])

    assert admin.delete(rule_url(rule)).status_code == 204
    assert not AutomationRule.objects.filter(pk=rule.pk).exists()


def test_patch_revalidates_keywords_against_the_trigger(admin, workspace):
    welcome = AutomationRuleFactory(workspace=workspace, trigger="first_inbound", keywords=[])
    price = AutomationRuleFactory(workspace=workspace)

    assert_invalid(
        admin.patch(rule_url(welcome), {"trigger": "keyword"}, format="json"), "keywords"
    )
    assert_invalid(admin.patch(rule_url(price), {"keywords": [" "]}, format="json"), "keywords")
    response = admin.patch(
        rule_url(welcome), {"trigger": "keyword", "keywords": ["hi"]}, format="json"
    )
    assert response.status_code == 200, response.content


def test_patch_number_revalidates_stored_template_actions(admin, workspace, number):
    template = MessageTemplateFactory(waba=number.waba, status=MessageTemplate.Status.APPROVED)
    rule = AutomationRuleFactory(
        workspace=workspace,
        actions=[
            template_action(
                template, [{"source": "static", "value": "a"}, {"source": "static", "value": "b"}]
            )
        ],
    )
    other_number = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)

    response = admin.patch(rule_url(rule), {"phone_number_id": str(other_number.pk)}, format="json")
    assert_invalid(response, "actions", 0, "config", "template_id")

    response = admin.patch(rule_url(rule), {"phone_number_id": str(number.pk)}, format="json")
    assert response.status_code == 200, response.content


def test_list_rules_with_filters(auth_client, workspace):
    price = AutomationRuleFactory(workspace=workspace)
    welcome = AutomationRuleFactory(
        workspace=workspace, trigger="first_inbound", keywords=[], is_active=False
    )
    client = auth_client(Role.VIEWER)

    assert result_ids(client.get(RULES)) == {str(price.pk), str(welcome.pk)}
    assert result_ids(client.get(RULES, {"trigger": "keyword"})) == {str(price.pk)}
    assert result_ids(client.get(RULES, {"is_active": "false"})) == {str(welcome.pk)}
    assert result_ids(client.get(RULES, {"is_active": "true", "trigger": "first_inbound"})) == set()
    assert_invalid(client.get(RULES, {"trigger": "birthday"}), "trigger")
    assert_invalid(client.get(RULES, {"is_active": "maybe"}), "is_active")


# --- Plan gate ----------------------------------------------------------------------------------


def test_keyword_rules_need_the_plan_feature(admin, no_keyword_feature):
    response = admin.post(RULES, rule_body(), format="json")

    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "feature_not_available"
    assert not AutomationRule.objects.exists()

    inactive = admin.post(RULES, rule_body(is_active=False), format="json")
    assert inactive.status_code == 201
    response = admin.patch(rule_url(inactive.json()["id"]), {"is_active": True}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "feature_not_available"

    welcome = admin.post(RULES, rule_body(trigger="first_inbound"), format="json")
    assert welcome.status_code == 201
    response = admin.patch(rule_url(welcome.json()["id"]), {"trigger": "keyword"}, format="json")
    assert response.status_code == 409
    assert AutomationRule.objects.get(pk=welcome.json()["id"]).trigger == "first_inbound"


def test_existing_keyword_rules_stay_editable_without_the_feature(
    admin, workspace, no_keyword_feature
):
    rule = AutomationRuleFactory(workspace=workspace)

    response = admin.patch(rule_url(rule), {"name": "Renamed", "keywords": ["rate"]}, format="json")
    assert response.status_code == 200, response.content
    assert admin.patch(rule_url(rule), {"is_active": False}, format="json").status_code == 200


def test_validation_errors_come_before_the_plan_gate(admin, no_keyword_feature):
    assert_invalid(admin.post(RULES, rule_body(actions=[]), format="json"), "actions")


# --- Business hours -----------------------------------------------------------------------------


def test_business_hours_are_created_lazily(auth_client, workspace):
    client = auth_client(Role.VIEWER)

    response = client.get(HOURS)

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "time_zone": "Asia/Kolkata", "schedule": []}
    client.get(HOURS)
    assert BusinessHours.objects.filter(workspace=workspace).count() == 1


def test_business_hours_time_zone_is_read_only_and_from_the_workspace(admin, workspace):
    workspace.time_zone = "Asia/Dubai"
    workspace.save(update_fields=["time_zone"])

    response = admin.patch(HOURS, {"time_zone": "UTC", "enabled": True}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["time_zone"] == "Asia/Dubai"
    assert response.json()["enabled"] is True


def test_patch_business_hours(admin, workspace):
    schedule = [
        {"day": 4, "start": "22:00", "end": "02:00"},
        {"day": 0, "start": "10:00", "end": "19:00"},
    ]

    response = admin.patch(HOURS, {"enabled": True, "schedule": schedule}, format="json")

    assert response.status_code == 200, response.content
    expected = [schedule[1], schedule[0]]  # stored sorted by day
    assert response.json()["schedule"] == expected
    hours = BusinessHours.objects.get(workspace=workspace)
    assert (hours.enabled, hours.schedule) == (True, expected)

    response = admin.patch(HOURS, {"enabled": False}, format="json")
    assert response.json() == {"enabled": False, "time_zone": "Asia/Kolkata", "schedule": expected}


def test_business_hours_are_per_workspace(auth_client, workspace, other_workspace):
    BusinessHoursFactory(workspace=other_workspace)

    assert auth_client().get(HOURS).json()["schedule"] == []


@pytest.mark.parametrize(
    "slot",
    [
        {"day": 7, "start": "09:00", "end": "18:00"},
        {"day": 0, "start": "24:00", "end": "18:00"},
        {"day": 0, "start": "9:00", "end": "18:00"},
        {"day": 0, "start": "09:00", "end": "09:00"},
        {"day": 0, "start": "09:00"},
    ],
)
def test_business_hours_validation(admin, slot):
    assert_invalid(admin.patch(HOURS, {"schedule": [slot]}, format="json"), "schedule")


# --- Runs ---------------------------------------------------------------------------------------


def test_runs_list_with_filters_newest_first(auth_client, workspace):
    rule = AutomationRuleFactory(workspace=workspace)
    other_rule = AutomationRuleFactory(workspace=workspace)
    old = AutomationRunFactory(rule=rule, message__conversation__workspace=workspace)
    new = AutomationRunFactory(
        rule=rule,
        message__conversation__workspace=workspace,
        status=AutomationRun.Status.SKIPPED,
        detail="Cooldown",
    )
    failed = AutomationRunFactory(
        rule=other_rule, message__conversation__workspace=workspace, status="failed"
    )
    AutomationRun.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=1))
    client = auth_client(Role.VIEWER)

    results = client.get(RUNS).json()["results"]

    assert results[-1]["id"] == str(old.pk)
    assert next(item for item in results if item["id"] == str(new.pk)) == {
        "id": str(new.pk),
        "rule": {"id": str(rule.pk), "name": rule.name},
        "conversation_id": str(new.conversation_id),
        "message_id": str(new.message_id),
        "status": "skipped",
        "detail": "Cooldown",
        "created_at": ANY,
    }
    assert result_ids(client.get(RUNS, {"rule": str(rule.pk)})) == {str(old.pk), str(new.pk)}
    assert result_ids(client.get(RUNS, {"status": "failed"})) == {str(failed.pk)}
    assert_invalid(client.get(RUNS, {"rule": "nope"}), "rule")
    assert_invalid(client.get(RUNS, {"status": "bogus"}), "status")
