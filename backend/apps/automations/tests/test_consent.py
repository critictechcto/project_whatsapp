"""The ``send_opt_in_request`` action, its config validation and the customer's tap."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.automations import consent
from apps.automations.engine import process_inbound
from apps.automations.factories import AutomationRuleFactory
from apps.automations.serializers import AutomationActionSerializer
from apps.contacts.models import ConsentEvent, Contact
from apps.inbox.models import Message

pytestmark = pytest.mark.django_db

REQUEST = {
    "type": "send_opt_in_request",
    "config": {
        "text": "Want offers on WhatsApp?",
        "yes_label": "Yes please",
        "no_label": "Not now",
        "confirmation_text": "Done, you're subscribed.",
        "decline_text": "No problem.",
    },
}


@pytest.fixture
def rule(workspace):
    return AutomationRuleFactory(workspace=workspace, keywords=["offers"], actions=[REQUEST])


@pytest.fixture
def unknown_contact(contact):
    contact.marketing_opt_in_status = Contact.OptInStatus.UNKNOWN
    contact.save(update_fields=["marketing_opt_in_status"])
    return contact


def automation_texts(conversation) -> list[str]:
    return list(
        Message.objects.filter(
            conversation=conversation, source=Message.Source.AUTOMATION, type=Message.Type.TEXT
        )
        .order_by("created_at")
        .values_list("text", flat=True)
    )


def tap(inbound, rule, answer: str, title: str = "Yes please"):
    message = inbound(title, type=Message.Type.INTERACTIVE)
    return message, consent.reply_id(answer, rule, 0)


# --- The action ---------------------------------------------------------------------------------


def test_action_sends_two_opt_in_buttons(rule, conversation, inbound):
    process_inbound(inbound("offers").pk)

    sent = Message.objects.get(conversation=conversation, source=Message.Source.AUTOMATION)
    assert sent.type == Message.Type.INTERACTIVE
    interactive = sent.payload["interactive"]
    assert interactive["body"] == {"text": "Want offers on WhatsApp?"}
    assert [button["reply"] for button in interactive["action"]["buttons"]] == [
        {"id": f"upc:consent:yes:{rule.pk}:0", "title": "Yes please"},
        {"id": f"upc:consent:no:{rule.pk}:0", "title": "Not now"},
    ]


def test_action_fails_outside_the_service_window(rule, conversation, inbound):
    message = inbound("offers")
    conversation.service_window_expires_at = timezone.now() - timedelta(minutes=1)
    conversation.save(update_fields=["service_window_expires_at"])

    run = process_inbound(message.pk)[0]

    assert run.status == "failed"
    assert run.action_results[0]["code"] == "outside_service_window"


# --- Config validation --------------------------------------------------------------------------


def clean(workspace, config: dict):
    serializer = AutomationActionSerializer(
        data={"type": "send_opt_in_request", "config": config}, context={"workspace": workspace}
    )
    valid = serializer.is_valid()
    return valid, serializer.validated_data if valid else serializer.errors


def test_config_defaults_the_button_labels(workspace):
    valid, data = clean(workspace, {"text": "  Offers?  "})

    assert valid
    assert data["config"] == {
        "text": "Offers?",
        "yes_label": consent.DEFAULT_YES_LABEL,
        "no_label": consent.DEFAULT_NO_LABEL,
        "confirmation_text": "",
        "decline_text": "",
    }


@pytest.mark.parametrize(
    ("config", "field"),
    [
        ({}, "text"),
        ({"text": " "}, "text"),
        ({"text": "x" * 1025}, "text"),
        ({"text": "Offers?", "yes_label": "y" * 21}, "yes_label"),
        ({"text": "Offers?", "yes_label": "Yes", "no_label": "yes"}, "no_label"),
    ],
)
def test_config_rejects_invalid_values(workspace, config, field):
    valid, errors = clean(workspace, config)

    assert not valid
    assert field in str(errors)


# --- The tap ------------------------------------------------------------------------------------


def test_yes_records_the_opt_in_and_confirms(rule, conversation, unknown_contact, inbound):
    message, reply_id = tap(inbound, rule, consent.YES)

    assert consent.handle_reply(message.pk, reply_id) == consent.YES
    assert consent.handle_reply(message.pk, reply_id) == consent.YES  # redelivered

    unknown_contact.refresh_from_db()
    assert unknown_contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_IN
    event = ConsentEvent.objects.get(contact=unknown_contact)
    assert (event.action, event.source, event.wamid) == ("opt_in", "whatsapp_button", message.wamid)
    assert "Yes please" in event.evidence
    assert automation_texts(conversation) == ["Done, you're subscribed."]


def test_no_changes_nothing_and_sends_the_decline_text(
    rule, conversation, unknown_contact, inbound
):
    message, reply_id = tap(inbound, rule, consent.NO, "Not now")

    assert consent.handle_reply(message.pk, reply_id) == consent.NO

    unknown_contact.refresh_from_db()
    assert unknown_contact.marketing_opt_in_status == Contact.OptInStatus.UNKNOWN
    assert not ConsentEvent.objects.exists()
    assert automation_texts(conversation) == ["No problem."]


def test_no_without_decline_text_sends_nothing(workspace, conversation, inbound):
    rule = AutomationRuleFactory(
        workspace=workspace,
        actions=[{**REQUEST, "config": {**REQUEST["config"], "decline_text": ""}}],
    )
    message, reply_id = tap(inbound, rule, consent.NO, "Not now")

    consent.handle_reply(message.pk, reply_id)

    assert automation_texts(conversation) == []


def test_a_deleted_rule_still_records_the_opt_in(rule, conversation, unknown_contact, inbound):
    message, reply_id = tap(inbound, rule, consent.YES)
    rule.delete()

    consent.handle_reply(message.pk, reply_id)

    unknown_contact.refresh_from_db()
    assert unknown_contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_IN
    assert automation_texts(conversation) == [consent.DEFAULT_CONFIRMATION]


@pytest.mark.parametrize(
    "reply_id",
    [
        None,
        "upc:shop:menu",
        "upc:consent:maybe:00000000-0000-0000-0000-000000000000:0",
        "upc:consent:yes:not-a-uuid:0",
        f"upc:consent:yes:{uuid.uuid4()}",
    ],
)
def test_other_ids_are_ignored(reply_id):
    assert consent.parse(reply_id) is None
