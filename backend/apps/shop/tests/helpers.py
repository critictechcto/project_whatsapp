from apps.inbox import interactive as limits
from apps.inbox.models import Message
from common.commerce import parse_reply_id
from common.events import MessageRecorded


def interactive_of(message: Message) -> dict:
    return message.payload["interactive"]


def body_of(message: Message) -> str:
    return interactive_of(message)["body"]["text"]


def button_ids(message: Message) -> list[str]:
    return [b["reply"]["id"] for b in interactive_of(message)["action"]["buttons"]]


def button_titles(message: Message) -> list[str]:
    return [b["reply"]["title"] for b in interactive_of(message)["action"]["buttons"]]


def rows(message: Message) -> list[dict]:
    return [row for s in interactive_of(message)["action"]["sections"] for row in s["rows"]]


def row_ids(message: Message) -> list[str]:
    return [row["id"] for row in rows(message)]


def assert_meta_limits(data: dict) -> None:
    """Meta's limits for an outbound ``interactive`` object built by the bot."""
    if "body" in data:
        assert 0 < len(data["body"]["text"]) <= limits.MAX_BODY
    if "footer" in data:
        assert len(data["footer"]["text"]) <= limits.MAX_FOOTER
    action = data.get("action", {})
    if data["type"] == "button":
        assert 1 <= len(action["buttons"]) <= limits.MAX_BUTTONS
        for button in action["buttons"]:
            assert len(button["reply"]["title"]) <= limits.MAX_BUTTON_TITLE
            assert parse_reply_id(button["reply"]["id"]) is not None
    elif data["type"] == "list":
        all_rows = [row for section in action["sections"] for row in section["rows"]]
        assert 1 <= len(all_rows) <= limits.MAX_LIST_ROWS
        assert len(action["button"]) <= limits.MAX_LIST_BUTTON
        for section in action["sections"]:
            assert len(section.get("title", "")) <= limits.MAX_SECTION_TITLE
        for row in all_rows:
            assert len(row["title"]) <= limits.MAX_ROW_TITLE
            assert len(row.get("description", "")) <= limits.MAX_ROW_DESCRIPTION
            assert len(row["id"]) <= limits.MAX_ROW_ID
            assert parse_reply_id(row["id"]) is not None


def assert_message_limits(message: Message) -> None:
    if message.type == Message.Type.INTERACTIVE:
        assert_meta_limits(interactive_of(message))


def recorded_event(message: Message, *, reply_id: str | None = None) -> MessageRecorded:
    conversation = message.conversation
    return MessageRecorded(
        workspace_id=message.workspace_id,
        message_id=message.pk,
        conversation_id=conversation.pk,
        contact_id=conversation.contact_id,
        phone_number_id=conversation.phone_number_id,
        direction=message.direction,
        source=message.source,
        source_ref=message.source_ref,
        type=message.type,
        text=message.text,
        reply_id=reply_id,
        wamid=message.wamid,
        is_first_inbound=False,
        contact_created=False,
        created_at=message.created_at,
    )
