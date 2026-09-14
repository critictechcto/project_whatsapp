"""Conversation operations (assign, close, reopen, notes, read receipts) and inbox event helpers.

Each operation sends a ``conversation.updated`` realtime frame on commit. Message frames
(``message.created``, ``message.status``) are sent by ``receivers.py`` from the inbox events.
"""

import logging
from datetime import datetime

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.message_templates import services as template_services
from apps.tenants.models import Membership
from apps.whatsapp.client.errors import GraphAPIError
from common import events, realtime

from .models import Conversation, ConversationNote, Message

logger = logging.getLogger(__name__)

MAX_NOTE_LENGTH = 10_000


# --- Conversations ------------------------------------------------------------------------------


def get_or_create_conversation(workspace_id, contact, phone_number) -> tuple[Conversation, bool]:
    """The conversation for ``(contact, phone_number)``; safe under concurrent creation."""
    return Conversation.objects.get_or_create(
        workspace_id=workspace_id, contact=contact, phone_number=phone_number
    )


def notify_conversation_updated(conversation: Conversation) -> None:
    """Send a ``conversation.updated`` frame to the workspace once the transaction commits."""
    realtime.broadcast(
        conversation.workspace_id, "conversation.updated", {"conversation_id": conversation.pk}
    )


def _update(conversation: Conversation, **fields) -> Conversation:
    Conversation.objects.filter(pk=conversation.pk).update(**fields, updated_at=timezone.now())
    conversation.refresh_from_db()
    notify_conversation_updated(conversation)
    return conversation


def assign(conversation: Conversation, user_or_none, *, actor) -> Conversation:
    """Assign to a member of the conversation's workspace, or unassign with ``None``."""
    if (
        user_or_none is not None
        and not Membership.objects.filter(
            workspace_id=conversation.workspace_id, user=user_or_none
        ).exists()
    ):
        raise ValidationError({"assignee_id": ["The assignee must be a member of this workspace."]})
    return _update(conversation, assignee=user_or_none)


def close(conversation: Conversation, *, actor) -> Conversation:
    return _update(conversation, status=Conversation.Status.CLOSED)


def reopen(conversation: Conversation, *, actor) -> Conversation:
    return _update(conversation, status=Conversation.Status.OPEN)


def add_note(conversation: Conversation, body: str, *, author) -> ConversationNote:
    body = (body or "").strip()
    if not body:
        raise ValidationError({"body": ["This field may not be blank."]})
    if len(body) > MAX_NOTE_LENGTH:
        raise ValidationError(
            {"body": [f"Ensure this field has no more than {MAX_NOTE_LENGTH} characters."]}
        )
    note = ConversationNote.objects.create(
        workspace_id=conversation.workspace_id,
        conversation=conversation,
        author=author,
        body=body,
    )
    notify_conversation_updated(conversation)
    return note


def mark_read(conversation: Conversation, *, actor) -> Conversation:
    """Reset ``unread_count`` and send Meta a read receipt for the latest inbound message.

    The receipt is only sent when there were unread messages; Graph errors are logged, not raised.
    """
    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
        had_unread = locked.unread_count > 0
        if had_unread:
            Conversation.objects.filter(pk=locked.pk).update(
                unread_count=0, updated_at=timezone.now()
            )
    if had_unread:
        notify_conversation_updated(conversation)
        _send_read_receipt(conversation)
    conversation.refresh_from_db()
    return conversation


def _send_read_receipt(conversation: Conversation) -> None:
    latest = (
        Message.objects.filter(
            conversation_id=conversation.pk,
            direction=Message.Direction.INBOUND,
            wamid__isnull=False,
        )
        .order_by(F("sent_at").desc(nulls_last=True), "-created_at")
        .first()
    )
    if latest is None:
        return
    phone = conversation.phone_number
    if not template_services.is_connected(phone.waba):
        return
    try:
        template_services.client_for(phone.waba).mark_read(phone.phone_number_id, latest.wamid)
    except GraphAPIError as exc:
        logger.info("Read receipt for message %s failed: %s", latest.pk, exc)


# --- Events -------------------------------------------------------------------------------------


def _emit_on_commit(signal, event) -> None:
    transaction.on_commit(lambda: events.emit(signal, event))


def emit_message_recorded(
    message: Message,
    conversation: Conversation,
    *,
    reply_id: str | None = None,
    is_first_inbound: bool = False,
    contact_created: bool = False,
) -> None:
    _emit_on_commit(
        events.message_recorded,
        events.MessageRecorded(
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
            is_first_inbound=is_first_inbound,
            contact_created=contact_created,
            created_at=message.created_at,
        ),
    )


def emit_delivery_updated(message: Message, *, occurred_at: datetime) -> None:
    _emit_on_commit(
        events.message_delivery_updated,
        events.MessageDeliveryUpdated(
            workspace_id=message.workspace_id,
            message_id=message.pk,
            conversation_id=message.conversation_id,
            source=message.source,
            source_ref=message.source_ref,
            status=message.status,
            error_code=message.error_code,
            occurred_at=occurred_at,
        ),
    )
