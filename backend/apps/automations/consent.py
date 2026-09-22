"""Opt-in buttons: the ``send_opt_in_request`` action and the customer's tap on them.

The action sends a message with two quick-reply buttons whose ids are
``upc:consent:<yes|no>:<rule_id>:<action_index>`` (the ``common.commerce`` grammar, so the tap is
claimed and never triggers automation rules). Tapping *yes* records a marketing opt-in (source
``whatsapp_button``) and sends the rule's confirmation text; tapping *no* changes nothing and sends
the decline text when the rule has one. A deleted or edited rule still records the opt-in (the
customer tapped it) and falls back to the default confirmation. Handling is idempotent: the consent
event is keyed on the tap's ``wamid`` and the reply on the tap message.
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from rest_framework.exceptions import APIException

from apps.contacts import services as contact_services
from apps.contacts.models import ConsentEvent
from apps.inbox import interactive, sending
from apps.inbox.models import Message
from common.commerce import build_reply_id, parse_reply_id

from .models import AutomationRule

logger = logging.getLogger(__name__)

ACTION_TYPE = "send_opt_in_request"
SCOPE = "consent"
YES, NO = "yes", "no"
DEFAULT_YES_LABEL = "Yes, send offers"
DEFAULT_NO_LABEL = "No thanks"
DEFAULT_CONFIRMATION = (
    "You're subscribed ✅ We'll send you offers and updates here. Reply STOP anytime to stop."
)


@dataclass(frozen=True, slots=True)
class ConsentReply:
    answer: str
    rule_id: uuid.UUID
    index: int


def reply_id(answer: str, rule: AutomationRule, index: int) -> str:
    return build_reply_id(SCOPE, answer, rule.pk, index)


def parse(value: object) -> ConsentReply | None:
    """The tapped opt-in button, or None when ``value`` is not one."""
    reply = parse_reply_id(value)
    if reply is None or reply.scope != SCOPE or reply.action not in (YES, NO):
        return None
    if len(reply.args) != 2 or not reply.args[1].isdigit():
        return None
    try:
        rule_id = uuid.UUID(reply.args[0])
    except ValueError:
        return None
    return ConsentReply(answer=reply.action, rule_id=rule_id, index=int(reply.args[1]))


def request_content(rule: AutomationRule, index: int, config: Mapping[str, Any]):
    """The interactive message for action ``index`` of ``rule``."""
    return interactive.reply_buttons(
        str(config.get("text") or ""),
        [
            (reply_id(YES, rule, index), str(config.get("yes_label") or DEFAULT_YES_LABEL)),
            (reply_id(NO, rule, index), str(config.get("no_label") or DEFAULT_NO_LABEL)),
        ],
    )


def _action_config(rule: AutomationRule | None, index: int) -> Mapping[str, Any]:
    actions = rule.actions if rule is not None and isinstance(rule.actions, list) else []
    action = actions[index] if index < len(actions) else None
    if isinstance(action, Mapping) and action.get("type") == ACTION_TYPE:
        config = action.get("config")
        return config if isinstance(config, Mapping) else {}
    return {}


def handle_reply(message_id, reply_id_value: str | None) -> str | None:
    """Record the answer to an opt-in button and reply. Returns the answer, or None if ignored."""
    tapped = parse(reply_id_value)
    if tapped is None:
        return None
    message = (
        Message.objects.select_related("workspace", "conversation__contact")
        .filter(pk=message_id, direction=Message.Direction.INBOUND)
        .first()
    )
    if message is None:
        return None
    conversation = message.conversation
    contact = conversation.contact
    rule = AutomationRule.objects.filter(
        workspace_id=message.workspace_id, pk=tapped.rule_id
    ).first()
    config = _action_config(rule, tapped.index)

    if tapped.answer == YES:
        contact_services.record_opt_in(
            contact,
            source=ConsentEvent.Source.WHATSAPP_BUTTON,
            evidence=f"Tapped {message.text.strip()!r} on an opt-in request sent on WhatsApp.",
            wamid=message.wamid or "",
            occurred_at=message.sent_at or message.created_at,
        )
        text = str(config.get("confirmation_text") or DEFAULT_CONFIRMATION)
    else:
        text = str(config.get("decline_text") or "")

    if text:
        try:
            sending.send_message(
                workspace=message.workspace,
                contact=contact,
                content=sending.TextContent(text),
                conversation=conversation,
                source=Message.Source.AUTOMATION,
                source_ref=str(rule.pk) if rule is not None else "",
                idempotency_key=f"consent-reply:{message.pk}",
            )
        except (APIException, ValueError) as exc:
            # The consent is recorded either way; a reply that can't be sent is only logged.
            logger.info("Opt-in reply for message %s not sent: %s", message.pk, exc)
    return tapped.answer
