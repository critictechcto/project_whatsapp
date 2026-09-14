"""Pure parsing of Meta webhook payloads into routable change items. No database access.

A delivery has ``entry[]`` (one per WABA) each with ``changes[]``; a ``messages`` change can carry
several messages and statuses. Every item becomes one :class:`ParsedChange` holding the target
event dataclass and its fields minus ``workspace_id``/``webhook_event_id``, which the processing
task adds after routing.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.dispatch import Signal

from common import events

logger = logging.getLogger(__name__)

WABA_OBJECT = "whatsapp_business_account"


@dataclass(frozen=True, slots=True)
class ParsedChange:
    event_class: type
    signal: Signal
    waba_id: str
    fields: Mapping[str, Any]
    # Routing prefers the phone number (messages field) and falls back to the WABA.
    phone_number_id: str | None = None
    field_name: str = ""

    def build(self, *, workspace_id, webhook_event_id=None):
        return self.event_class(
            **self.fields, workspace_id=workspace_id, webhook_event_id=webhook_event_id
        )


class MalformedItem(ValueError):
    """A single message/status/change is missing required data; it is skipped."""


def parse_timestamp(value: Any) -> datetime:
    """Meta timestamps are epoch seconds as strings; return an aware UTC datetime."""
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise MalformedItem(f"invalid timestamp {value!r}") from exc


def _str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _require(mapping: Mapping[str, Any], key: str) -> Any:
    value = mapping.get(key)
    if value is None or value == "":
        raise MalformedItem(f"missing {key!r}")
    return value


def parse_payload(payload: Any) -> list[ParsedChange]:
    """Turn a whole webhook body into change items. Unknown objects/fields are ignored."""
    if not isinstance(payload, Mapping):
        logger.warning("Webhook payload is not an object; ignoring")
        return []
    object_type = payload.get("object")
    if object_type != WABA_OBJECT:
        logger.warning("Ignoring webhook for unsupported object %r", object_type)
        return []

    items: list[ParsedChange] = []
    for entry in _list(payload.get("entry")):
        waba_id = str(entry.get("id") or "")
        for change in _list(entry.get("changes")):
            field_name = change.get("field")
            value = change.get("value")
            if not isinstance(value, Mapping):
                logger.warning("Webhook change %r has no value object; skipping", field_name)
                continue
            parser = FIELD_PARSERS.get(field_name)
            if parser is None:
                logger.info("Ignoring unsupported webhook field %r (WABA %s)", field_name, waba_id)
                continue
            items.extend(parser(waba_id, value))
    return items


def _list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


# --- messages -------------------------------------------------------------------------------


def parse_messages_change(waba_id: str, value: Mapping[str, Any]) -> list[ParsedChange]:
    metadata = value.get("metadata") or {}
    phone_number_id = _str_or_none(metadata.get("phone_number_id"))
    profile_names = {
        str(contact.get("wa_id")): (contact.get("profile") or {}).get("name")
        for contact in _list(value.get("contacts"))
        if contact.get("wa_id")
    }

    items: list[ParsedChange] = []
    for message in _list(value.get("messages")):
        try:
            fields = parse_message(message, profile_names)
        except MalformedItem as exc:
            logger.warning("Skipping malformed inbound message: %s", exc)
            continue
        items.append(
            ParsedChange(
                event_class=events.InboundMessage,
                signal=events.inbound_message_received,
                waba_id=waba_id,
                phone_number_id=phone_number_id,
                field_name="messages",
                fields={"waba_id": waba_id, "phone_number_id": phone_number_id or "", **fields},
            )
        )
    for status in _list(value.get("statuses")):
        try:
            fields = parse_status(status)
        except MalformedItem as exc:
            logger.warning("Skipping malformed message status: %s", exc)
            continue
        items.append(
            ParsedChange(
                event_class=events.MessageStatus,
                signal=events.message_status_updated,
                waba_id=waba_id,
                phone_number_id=phone_number_id,
                field_name="messages",
                fields={"waba_id": waba_id, "phone_number_id": phone_number_id or "", **fields},
            )
        )
    if phone_number_id is None and items:
        logger.warning("messages change without metadata.phone_number_id (WABA %s)", waba_id)
    return items


def parse_message(
    message: Mapping[str, Any], profile_names: Mapping[str, str | None] | None = None
) -> dict[str, Any]:
    """Fields of :class:`common.events.InboundMessage` for one ``value.messages[]`` item."""
    from_wa_id = str(_require(message, "from"))
    message_type = str(message.get("type") or "unsupported")
    body = message.get(message_type)
    body = body if isinstance(body, Mapping) else {}
    text, reply_id, context_wamid = _message_content(message_type, body)
    context = message.get("context")
    if context_wamid is None and isinstance(context, Mapping):
        context_wamid = _str_or_none(context.get("id"))
    return {
        "wamid": str(_require(message, "id")),
        "from_wa_id": from_wa_id,
        "timestamp": parse_timestamp(message.get("timestamp")),
        "type": message_type,
        "text": text,
        "reply_id": reply_id,
        "profile_name": (profile_names or {}).get(from_wa_id),
        "context_wamid": context_wamid,
        "payload": dict(message),
    }


def _message_content(
    message_type: str, body: Mapping[str, Any]
) -> tuple[str | None, str | None, str | None]:
    """``(text, reply_id, context_wamid)`` for a message body by type."""
    if message_type == "text":
        return _str_or_none(body.get("body")), None, None
    if message_type in ("image", "video", "document"):
        return _str_or_none(body.get("caption")), None, None
    if message_type == "button":
        return _str_or_none(body.get("text")), _str_or_none(body.get("payload")), None
    if message_type == "interactive":
        reply = body.get(str(body.get("type"))) if body.get("type") else None
        if body.get("type") in ("button_reply", "list_reply") and isinstance(reply, Mapping):
            return _str_or_none(reply.get("title")), _str_or_none(reply.get("id")), None
        return None, None, None
    if message_type == "reaction":
        return _str_or_none(body.get("emoji")), None, _str_or_none(body.get("message_id"))
    if message_type == "location":
        return _str_or_none(body.get("name")) or _str_or_none(body.get("address")), None, None
    return None, None, None


def parse_status(status: Mapping[str, Any]) -> dict[str, Any]:
    """Fields of :class:`common.events.MessageStatus` for one ``value.statuses[]`` item."""
    conversation = status.get("conversation")
    pricing = status.get("pricing")
    conversation = conversation if isinstance(conversation, Mapping) else {}
    pricing = pricing if isinstance(pricing, Mapping) else {}
    billable = pricing.get("billable")
    return {
        "wamid": str(_require(status, "id")),
        "recipient_wa_id": str(_require(status, "recipient_id")),
        "status": str(_require(status, "status")),
        "timestamp": parse_timestamp(status.get("timestamp")),
        "conversation_id": _str_or_none(conversation.get("id")),
        "pricing_category": _str_or_none(pricing.get("category")),
        "pricing_model": _str_or_none(pricing.get("pricing_model")),
        "billable": billable if isinstance(billable, bool) else None,
        "errors": tuple(parse_error(error) for error in _list(status.get("errors"))),
        "payload": dict(status),
    }


def parse_error(error: Mapping[str, Any]) -> events.MetaError:
    error_data = error.get("error_data")
    details = error_data.get("details") if isinstance(error_data, Mapping) else None
    try:
        code = int(error.get("code"))
    except (TypeError, ValueError):
        code = 0
    return events.MetaError(
        code=code,
        title=str(error.get("title") or ""),
        message=str(error.get("message") or ""),
        details=str(details or ""),
    )


# --- WABA-level fields (routed by entry.id) -------------------------------------------------


def _template_identity(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "meta_template_id": str(_require(value, "message_template_id")),
        "name": str(value.get("message_template_name") or ""),
        "language": str(value.get("message_template_language") or ""),
    }


def _single(field_name: str, event_class: type, signal: Signal, build_fields):
    def parse(waba_id: str, value: Mapping[str, Any]) -> list[ParsedChange]:
        if not waba_id:
            logger.warning("Webhook %r change without entry.id; skipping", field_name)
            return []
        try:
            fields = build_fields(value)
        except MalformedItem as exc:
            logger.warning("Skipping malformed %r change: %s", field_name, exc)
            return []
        return [
            ParsedChange(
                event_class=event_class,
                signal=signal,
                waba_id=waba_id,
                field_name=field_name,
                fields={"waba_id": waba_id, **fields, "payload": dict(value)},
            )
        ]

    return parse


def template_status_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    reason = _str_or_none(value.get("reason"))
    return {
        **_template_identity(value),
        "event": str(_require(value, "event")),
        "reason": None if reason == "NONE" else reason,
    }


def template_category_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_template_identity(value),
        "previous_category": str(value.get("previous_category") or ""),
        "new_category": str(_require(value, "new_category")),
    }


def template_quality_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_template_identity(value),
        "previous_quality_score": str(value.get("previous_quality_score") or ""),
        "new_quality_score": str(_require(value, "new_quality_score")),
    }


def phone_number_quality_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "display_phone_number": str(_require(value, "display_phone_number")),
        "event": str(_require(value, "event")),
        "current_limit": _str_or_none(value.get("current_limit")),
        "old_limit": _str_or_none(value.get("old_limit")),
    }


def account_update_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"event": str(_require(value, "event"))}


FIELD_PARSERS = {
    "messages": parse_messages_change,
    "message_template_status_update": _single(
        "message_template_status_update",
        events.TemplateStatusUpdate,
        events.template_status_updated,
        template_status_fields,
    ),
    "template_category_update": _single(
        "template_category_update",
        events.TemplateCategoryUpdate,
        events.template_category_updated,
        template_category_fields,
    ),
    "message_template_quality_update": _single(
        "message_template_quality_update",
        events.TemplateQualityUpdate,
        events.template_quality_updated,
        template_quality_fields,
    ),
    "phone_number_quality_update": _single(
        "phone_number_quality_update",
        events.PhoneNumberQualityUpdate,
        events.phone_number_quality_updated,
        phone_number_quality_fields,
    ),
    "account_update": _single(
        "account_update",
        events.AccountUpdate,
        events.account_updated,
        account_update_fields,
    ),
}
