"""``manage.py sync_platform_templates``."""

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.message_templates import validators
from apps.seller_alerts.content import NEW_ORDER, ORDER_ATTENTION, PLATFORM_TEMPLATES, SELLER_VERIFY
from apps.whatsapp.client.errors import InvalidParameterError, TokenInvalidError, TransientError


def run() -> str:
    out = StringIO()
    call_command("sync_platform_templates", stdout=out)
    return out.getvalue()


def test_definitions_pass_template_validation():
    for template in PLATFORM_TEMPLATES:
        validators.validate_template(**template.definition())


def test_creates_the_missing_templates(fake_graph):
    output = run()

    creates = fake_graph.calls_to("create_template")
    assert [call.kwargs["template"]["name"] for call in creates] == [
        "upc_seller_verify",
        "upc_new_order",
        "upc_order_attention",
    ]
    assert {call.kwargs["waba_id"] for call in creates} == {settings.PLATFORM_WA_WABA_ID}
    assert {call.access_token for call in fake_graph.calls} == {settings.PLATFORM_WA_ACCESS_TOKEN}
    new_order = creates[1].kwargs["template"]
    assert new_order["category"] == "UTILITY"
    assert new_order["language"] == "en"
    [body, buttons] = new_order["components"]
    assert body["text"].count("{{") == 5
    assert len(body["example"]["body_text"][0]) == 5
    assert [button["text"] for button in buttons["buttons"]] == [
        "Mark packed",
        "Mark shipped",
        "Cancel",
    ]
    assert {button["type"] for button in buttons["buttons"]} == {"QUICK_REPLY"}
    assert [c["type"] for c in creates[0].kwargs["template"]["components"]] == ["BODY", "BUTTONS"]
    assert [c["type"] for c in creates[2].kwargs["template"]["components"]] == ["BODY"]
    assert "upc_new_order (en, UTILITY): PENDING [created]" in output


def test_is_idempotent_and_prints_statuses(fake_graph):
    run()
    for template in fake_graph.templates.values():
        if template["name"] == "upc_new_order":
            template["status"] = "APPROVED"

    output = run()

    assert len(fake_graph.calls_to("create_template")) == 3
    assert "upc_seller_verify (en, UTILITY): PENDING [unchanged]" in output
    assert "upc_new_order (en, UTILITY): APPROVED [unchanged]" in output
    assert "upc_order_attention (en, UTILITY): PENDING [unchanged]" in output


OLD_COMPONENTS = [{"type": "BODY", "text": "Old text {{1}}."}]


@pytest.fixture
def old_template(fake_graph):
    def add(status: str, template=ORDER_ATTENTION, **fields):
        return fake_graph.add_template(
            settings.PLATFORM_WA_WABA_ID,
            name=template.name,
            language="en",
            status=status,
            components=OLD_COMPONENTS,
            **fields,
        )

    return add


def test_edits_a_template_that_differs(fake_graph, old_template):
    old = old_template("REJECTED")
    fake_graph.add_template(
        settings.PLATFORM_WA_WABA_ID, status="APPROVED", **SELLER_VERIFY.definition()
    )
    fake_graph.add_template("another-waba", name=NEW_ORDER.name, language="en")

    output = run()

    assert [call.kwargs["template"]["name"] for call in fake_graph.calls_to("create_template")] == [
        "upc_new_order"
    ]
    [edit] = fake_graph.calls_to("edit_message_template")
    assert edit.kwargs == {
        "template_id": old["id"],
        "components": ORDER_ATTENTION.definition()["components"],
        "category": None,
    }
    assert edit.access_token == settings.PLATFORM_WA_ACCESS_TOKEN
    assert "upc_order_attention (en, UTILITY): PENDING [updated]" in output
    assert "upc_seller_verify (en, UTILITY): APPROVED [unchanged]" in output
    assert ORDER_ATTENTION.matches(fake_graph.templates[old["id"]]["components"])

    second = run()

    assert len(fake_graph.calls_to("edit_message_template")) == 1
    assert "upc_order_attention (en, UTILITY): PENDING [unchanged]" in second


def test_an_approved_template_keeps_its_category(fake_graph, old_template):
    old = old_template("APPROVED", category="MARKETING")

    output = run()

    [edit] = fake_graph.calls_to("edit_message_template")
    assert edit.kwargs["category"] is None
    assert "upc_order_attention (en, MARKETING): APPROVED [updated]" in output
    assert fake_graph.templates[old["id"]]["category"] == "MARKETING"


def test_a_rejected_template_gets_its_category_back(fake_graph, old_template):
    old = old_template("REJECTED", category="MARKETING")

    output = run()

    [edit] = fake_graph.calls_to("edit_message_template")
    assert edit.kwargs["category"] == "UTILITY"
    assert "upc_order_attention (en, UTILITY): PENDING [updated]" in output
    assert fake_graph.templates[old["id"]]["category"] == "UTILITY"


@pytest.mark.parametrize("status", ["PENDING", "DISABLED", "IN_APPEAL"])
def test_a_status_meta_cannot_edit_is_reported(fake_graph, old_template, status):
    old_template(status)

    output = run()

    assert fake_graph.calls_to("edit_message_template") == []
    assert (
        f"upc_order_attention (en, UTILITY): {status} "
        f"[outdated: Meta doesn't allow edits while the template is {status}]"
    ) in output


def test_the_edit_limit_is_reported(fake_graph, old_template):
    old = old_template("APPROVED")
    fake_graph.fail(
        "edit_message_template",
        InvalidParameterError("You have reached the edit limit for this template.", code=100),
    )

    output = run()

    assert (
        "upc_order_attention (en, UTILITY): APPROVED "
        "[outdated: Meta refused the edit: You have reached the edit limit for this template.]"
    ) in output
    assert fake_graph.templates[old["id"]]["components"] == OLD_COMPONENTS


def test_retryable_edit_errors_fail_the_command(fake_graph, old_template):
    old_template("APPROVED")
    fake_graph.fail("edit_message_template", TransientError("Service unavailable", code=2))

    with pytest.raises(CommandError, match="Service unavailable"):
        run()


@pytest.mark.parametrize("setting", ["PLATFORM_WA_WABA_ID", "PLATFORM_WA_ACCESS_TOKEN"])
def test_fails_clearly_without_settings(fake_graph, settings, setting):
    setattr(settings, setting, "")

    with pytest.raises(CommandError, match=setting):
        run()

    assert fake_graph.calls == []


def test_graph_errors_become_command_errors(fake_graph):
    fake_graph.fail("list_templates", TokenInvalidError("Session expired", code=190))

    with pytest.raises(CommandError, match="Session expired"):
        run()
