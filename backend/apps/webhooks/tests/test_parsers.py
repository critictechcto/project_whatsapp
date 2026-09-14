import copy
import uuid
from datetime import UTC, datetime

import pytest

from apps.webhooks.parsers import MalformedItem, parse_payload, parse_timestamp
from common import events

from .helpers import (
    OTHER_PHONE_NUMBER_ID,
    OTHER_WABA_ID,
    PAYLOADS,
    PHONE_NUMBER_ID,
    WABA_ID,
    load_payload,
)

WAMID_REPLIED_TO = "wamid.HBgMOTE5ODc2NTQzMjEwFQIAERgSQzVEQjM4MzA0QzZENTc3MDVBAA=="
WAMID_TEMPLATE = "wamid.HBgMOTE5ODc2NTQzMjEwFQIAERgSNkQ3RjI5QTFCMEU4NDVCNzI0AA=="


def ts(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


def only(name: str):
    items = parse_payload(load_payload(name))
    assert len(items) == 1, items
    return items[0]


def first_message(payload: dict) -> dict:
    return payload["entry"][0]["changes"][0]["value"]["messages"][0]


@pytest.mark.parametrize("path", sorted(PAYLOADS.glob("*.json")), ids=lambda p: p.stem)
def test_every_fixture_builds_its_event_dataclass(path):
    workspace_id, webhook_event_id = uuid.uuid4(), uuid.uuid4()
    for item in parse_payload(load_payload(path.name)):
        event = item.build(workspace_id=workspace_id, webhook_event_id=webhook_event_id)
        assert isinstance(event, item.event_class)
        assert event.workspace_id == workspace_id
        assert event.webhook_event_id == webhook_event_id


def test_text_message():
    item = only("text_message.json")

    assert item.event_class is events.InboundMessage
    assert item.signal is events.inbound_message_received
    assert (item.waba_id, item.phone_number_id) == (WABA_ID, PHONE_NUMBER_ID)
    fields = item.fields
    assert fields["waba_id"] == WABA_ID
    assert fields["phone_number_id"] == PHONE_NUMBER_ID
    assert fields["wamid"].startswith("wamid.")
    assert fields["from_wa_id"] == "919876543210"
    assert fields["type"] == "text"
    assert fields["text"] == "Hi, is the Diwali offer still available?"
    assert fields["reply_id"] is None
    assert fields["context_wamid"] is None
    assert fields["profile_name"] == "Priya Sharma"
    assert fields["timestamp"] == ts(1757830000)
    assert fields["timestamp"].tzinfo is UTC
    assert fields["payload"]["text"]["body"] == fields["text"]


def test_image_with_caption():
    fields = only("image_caption.json").fields

    assert fields["type"] == "image"
    assert fields["text"] == "Order #1042 arrived damaged"
    assert fields["payload"]["image"]["id"] == "1003383421387256"


def test_interactive_button_reply():
    fields = only("interactive_button_reply.json").fields

    assert fields["type"] == "interactive"
    assert fields["text"] == "Confirm"
    assert fields["reply_id"] == "confirm_booking"
    assert fields["context_wamid"] == WAMID_REPLIED_TO


def test_interactive_list_reply():
    payload = load_payload("interactive_button_reply.json")
    first_message(payload)["interactive"] = {
        "type": "list_reply",
        "list_reply": {"id": "slot_4pm", "title": "4 PM", "description": "Bandra store"},
    }

    [item] = parse_payload(payload)

    assert (item.fields["text"], item.fields["reply_id"]) == ("4 PM", "slot_4pm")


def test_interactive_flow_reply_has_no_text():
    payload = load_payload("interactive_button_reply.json")
    first_message(payload)["interactive"] = {
        "type": "nfm_reply",
        "nfm_reply": {"name": "flow", "body": "Sent", "response_json": "{}"},
    }

    [item] = parse_payload(payload)

    assert (item.fields["text"], item.fields["reply_id"]) == (None, None)


def test_template_quick_reply_button():
    fields = only("template_button_reply.json").fields

    assert fields["type"] == "button"
    assert fields["text"] == "Stop promotions"
    assert fields["reply_id"] == "STOP_PROMOTIONS"
    assert fields["context_wamid"] == WAMID_TEMPLATE


def test_reaction():
    fields = only("reaction.json").fields

    assert fields["type"] == "reaction"
    assert fields["text"] == "\N{THUMBS UP SIGN}"
    assert fields["context_wamid"] == WAMID_REPLIED_TO


def test_location_uses_name_then_address():
    assert only("location.json").fields["text"] == "Bandra Store"

    payload = load_payload("location.json")
    del first_message(payload)["location"]["name"]
    [item] = parse_payload(payload)

    assert item.fields["text"] == "Linking Road, Bandra West, Mumbai, Maharashtra 400050"


def test_other_message_types_have_no_text():
    payload = load_payload("text_message.json")
    message = first_message(payload)
    del message["text"]
    message["type"] = "sticker"
    message["sticker"] = {"mime_type": "image/webp", "id": "7890", "animated": False}

    [item] = parse_payload(payload)

    assert item.fields["type"] == "sticker"
    assert item.fields["text"] is None
    assert item.fields["payload"]["sticker"]["id"] == "7890"


@pytest.mark.parametrize(
    ("name", "status", "timestamp", "conversation_id", "category", "billable"),
    [
        (
            "status_sent.json",
            "sent",
            1757830400,
            "6ceb9d929c1f2c1c6a8a4b1e2f3d4c5b",
            "marketing",
            True,
        ),
        (
            "status_delivered.json",
            "delivered",
            1757830405,
            "6ceb9d929c1f2c1c6a8a4b1e2f3d4c5b",
            "marketing",
            True,
        ),
        ("status_read.json", "read", 1757830500, None, None, None),
    ],
)
def test_statuses(name, status, timestamp, conversation_id, category, billable):
    item = only(name)

    assert item.event_class is events.MessageStatus
    assert item.signal is events.message_status_updated
    assert item.phone_number_id == PHONE_NUMBER_ID
    fields = item.fields
    assert fields["wamid"] == WAMID_TEMPLATE
    assert fields["recipient_wa_id"] == "919876543210"
    assert fields["status"] == status
    assert fields["timestamp"] == ts(timestamp)
    assert fields["conversation_id"] == conversation_id
    assert fields["pricing_category"] == category
    assert fields["pricing_model"] == ("PMP" if category else None)
    assert fields["billable"] is billable
    assert fields["errors"] == ()


def test_failed_status_errors():
    item = only("status_failed.json")
    event = item.build(workspace_id=uuid.uuid4())

    assert event.status == "failed"
    assert event.recipient_wa_id == "919812345678"
    [error] = event.errors
    assert error.code == 131050
    assert error.title.startswith("Unable to deliver the message")
    assert error.message.startswith("Unable to deliver the message")
    assert error.details == "The recipient has stopped marketing messages from this business."
    assert event.error_codes == frozenset({131050})


def test_batched_entries_and_changes():
    items = parse_payload(load_payload("batched.json"))

    assert [item.event_class for item in items] == [
        events.InboundMessage,
        events.InboundMessage,
        events.MessageStatus,
        events.TemplateStatusUpdate,
        events.MessageStatus,
    ]
    first, second, status, template, other_status = items
    assert first.fields["profile_name"] == "Priya Sharma"
    assert second.fields["profile_name"] == "Rahul Verma"
    assert second.fields["text"] == "Price list please"
    assert status.fields["billable"] is False
    assert template.phone_number_id is None
    assert template.waba_id == WABA_ID
    assert template.fields["name"] == "festive_greeting"
    assert (other_status.waba_id, other_status.phone_number_id) == (
        OTHER_WABA_ID,
        OTHER_PHONE_NUMBER_ID,
    )


def test_template_approved():
    item = only("template_approved.json")

    assert item.event_class is events.TemplateStatusUpdate
    assert item.signal is events.template_status_updated
    assert (item.waba_id, item.phone_number_id) == (WABA_ID, None)
    assert item.fields == {
        "waba_id": WABA_ID,
        "meta_template_id": "1689556908129832",
        "name": "diwali_offer_2026",
        "language": "en_US",
        "event": "APPROVED",
        "reason": None,
        "payload": load_payload("template_approved.json")["entry"][0]["changes"][0]["value"],
    }


def test_template_rejected_keeps_reason_and_raw_info():
    fields = only("template_rejected.json").fields

    assert fields["event"] == "REJECTED"
    assert fields["reason"] == "INVALID_FORMAT"
    assert fields["meta_template_id"] == "1689556908129833"
    assert fields["language"] == "hi"
    assert fields["payload"]["other_info"]["title"] == "FORMATTING"


def test_template_category_update():
    item = only("template_category_update.json")

    assert item.event_class is events.TemplateCategoryUpdate
    assert item.signal is events.template_category_updated
    assert item.fields["meta_template_id"] == "1689556908129834"
    assert item.fields["name"] == "payment_reminder"
    assert item.fields["previous_category"] == "UTILITY"
    assert item.fields["new_category"] == "MARKETING"


def test_template_quality_update():
    item = only("template_quality_update.json")

    assert item.event_class is events.TemplateQualityUpdate
    assert item.signal is events.template_quality_updated
    assert item.fields["previous_quality_score"] == "GREEN"
    assert item.fields["new_quality_score"] == "YELLOW"
    assert item.fields["language"] == "en_US"


def test_phone_number_quality_downgrade():
    item = only("phone_number_quality_downgrade.json")

    assert item.event_class is events.PhoneNumberQualityUpdate
    assert item.signal is events.phone_number_quality_updated
    assert (item.waba_id, item.phone_number_id) == (WABA_ID, None)
    assert item.fields["display_phone_number"] == "15550783881"
    assert item.fields["event"] == "DOWNGRADE"
    assert item.fields["current_limit"] == "TIER_1K"
    assert item.fields["old_limit"] == "TIER_10K"


def test_phone_number_quality_without_old_limit():
    payload = load_payload("phone_number_quality_downgrade.json")
    del payload["entry"][0]["changes"][0]["value"]["old_limit"]

    [item] = parse_payload(payload)

    assert item.fields["old_limit"] is None


def test_account_update():
    item = only("account_update.json")

    assert item.event_class is events.AccountUpdate
    assert item.signal is events.account_updated
    assert item.fields["event"] == "ACCOUNT_VIOLATION"
    assert item.fields["payload"]["violation_info"] == {"violation_type": "SCAM"}


def test_unknown_field_is_ignored(caplog):
    caplog.set_level("INFO", logger="apps.webhooks.parsers")

    assert parse_payload(load_payload("unknown_field.json")) == []
    assert "business_capability_update" in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "text",
        {"object": "page", "entry": [{"id": "1", "changes": []}]},
        {"object": "whatsapp_business_account"},
        {"object": "whatsapp_business_account", "entry": "nope"},
        {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{}]}]},
    ],
)
def test_unsupported_or_empty_payloads(payload):
    assert parse_payload(payload) == []


def test_malformed_items_are_skipped_but_others_kept():
    payload = load_payload("batched.json")
    value = payload["entry"][0]["changes"][0]["value"]
    del value["messages"][0]["id"]
    value["statuses"][0]["timestamp"] = "not-a-number"

    items = parse_payload(copy.deepcopy(payload))

    kinds = [item.event_class for item in items]
    assert kinds.count(events.InboundMessage) == 1
    assert kinds.count(events.MessageStatus) == 1  # the other entry's status
    assert kinds.count(events.TemplateStatusUpdate) == 1


@pytest.mark.parametrize("value", [None, "", "abc", "1.5"])
def test_parse_timestamp_rejects_invalid(value):
    with pytest.raises(MalformedItem):
        parse_timestamp(value)
