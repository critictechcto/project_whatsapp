"""``manage.py sync_platform_templates``."""

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.message_templates import validators
from apps.seller_alerts.content import NEW_ORDER, ORDER_ATTENTION, PLATFORM_TEMPLATES, SELLER_VERIFY
from apps.whatsapp.client.errors import TokenInvalidError


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


def test_reports_a_template_that_differs(fake_graph):
    waba_id = settings.PLATFORM_WA_WABA_ID
    fake_graph.add_template(
        waba_id,
        name=ORDER_ATTENTION.name,
        language="en",
        status="REJECTED",
        components=[{"type": "BODY", "text": "Old text {{1}}."}],
    )
    fake_graph.add_template(waba_id, status="APPROVED", **SELLER_VERIFY.definition())
    fake_graph.add_template("another-waba", name=NEW_ORDER.name, language="en")

    output = run()

    assert [call.kwargs["template"]["name"] for call in fake_graph.calls_to("create_template")] == [
        "upc_new_order"
    ]
    assert "upc_order_attention (en, UTILITY): REJECTED [outdated]" in output
    assert "upc_seller_verify (en, UTILITY): APPROVED [unchanged]" in output


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
