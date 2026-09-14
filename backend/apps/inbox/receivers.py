"""Store inbound WhatsApp messages and apply delivery statuses. Every receiver is idempotent:
webhook retries re-emit every event of a delivery."""

import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F
from django.dispatch import receiver
from django.utils import timezone

from apps.contacts import services as contact_services
from apps.whatsapp.models import PhoneNumber
from common.events import (
    InboundMessage,
    MessageStatus,
    inbound_message_received,
    message_status_updated,
)
from common.phone import InvalidPhoneNumber

from . import services
from .models import Conversation, Message

logger = logging.getLogger(__name__)

Status = Message.Status

SERVICE_WINDOW = timedelta(hours=24)
# A status can arrive before dispatch stores the wamid: retry the webhook while it is recent.
UNKNOWN_WAMID_RETRY_WINDOW = timedelta(minutes=10)
# A contact created within this long of the message's Meta timestamp counts as created by it.
CONTACT_CREATED_TOLERANCE = timedelta(seconds=60)
# Meta message types that do not come from the customer and so don't open the window.
NON_CUSTOMER_TYPES = frozenset({"system"})

STATUS_RANK = {Status.SENT: 1, Status.DELIVERED: 2, Status.READ: 3}


class StatusForUnknownMessage(LookupError):
    """A status for a wamid that is not stored yet; raising makes the webhook retry."""


def _later(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None or candidate > current else current


# --- Inbound messages ---------------------------------------------------------------------------


@receiver(inbound_message_received, dispatch_uid="inbox.on_inbound_message")
def on_inbound_message(sender, event: InboundMessage, **kwargs) -> None:
    phone = (
        PhoneNumber.objects.select_related("workspace")
        .filter(workspace_id=event.workspace_id, phone_number_id=event.phone_number_id)
        .first()
    )
    if phone is None:
        logger.warning(
            "Inbound message %s for unknown phone number %s", event.wamid, event.phone_number_id
        )
        return
    if _already_stored(event.wamid, phone.workspace_id):
        return
    try:
        contact = contact_services.get_or_create_from_wa(
            phone.workspace, event.from_wa_id, profile_name=event.profile_name
        )
    except InvalidPhoneNumber:
        logger.warning("Ignoring inbound message %s with invalid wa_id", event.wamid)
        return
    conversation, _ = services.get_or_create_conversation(phone.workspace_id, contact, phone)

    with transaction.atomic():
        # The lock serialises inbound processing per conversation, so the checks below are exact.
        locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if _already_stored(event.wamid, phone.workspace_id):
            return
        is_first_inbound = not Message.objects.filter(
            conversation=locked, direction=Message.Direction.INBOUND
        ).exists()
        contact_created = (
            contact.created_at >= event.timestamp - CONTACT_CREATED_TOLERANCE
            and not Message.objects.filter(conversation__contact=contact).exists()
        )
        message = Message.objects.create(
            workspace_id=phone.workspace_id,
            conversation=locked,
            direction=Message.Direction.INBOUND,
            status=Status.RECEIVED,
            source=Message.Source.INBOUND,
            wamid=event.wamid,
            sent_at=event.timestamp,
            reply_to_wamid=event.context_wamid or "",
            reply_to=(
                Message.objects.filter(
                    workspace_id=phone.workspace_id, wamid=event.context_wamid
                ).first()
                if event.context_wamid
                else None
            ),
            **_content_fields(event),
        )

        now = timezone.now()
        fields: dict = {
            "last_message_at": _later(locked.last_message_at, event.timestamp),
            "updated_at": now,
        }
        if event.type not in NON_CUSTOMER_TYPES:
            fields["last_inbound_at"] = _later(locked.last_inbound_at, event.timestamp)
            fields["service_window_expires_at"] = _later(
                locked.service_window_expires_at, event.timestamp + SERVICE_WINDOW
            )
            fields["unread_count"] = F("unread_count") + 1
            if locked.status == Conversation.Status.CLOSED:
                fields["status"] = Conversation.Status.OPEN
        Conversation.objects.filter(pk=locked.pk).update(**fields)

        services.emit_message_recorded(
            message,
            locked,
            reply_id=event.reply_id,
            is_first_inbound=is_first_inbound,
            contact_created=contact_created,
        )
        if message.media_id:
            from .tasks import download_media

            message_pk = str(message.pk)
            transaction.on_commit(lambda: download_media.delay(message_pk), robust=True)


def _already_stored(wamid: str, workspace_id) -> bool:
    owner = Message.objects.filter(wamid=wamid).values_list("workspace_id", flat=True).first()
    if owner is not None and owner != workspace_id:
        logger.warning("Inbound wamid %s is already stored for another workspace", wamid)
    return owner is not None


def _content_fields(event: InboundMessage) -> dict:
    message_type = event.type if event.type in Message.Type.values else Message.Type.UNSUPPORTED
    fields = {
        "type": message_type,
        "text": event.text or "",
        "payload": dict(event.payload),
    }
    if message_type in Message.MEDIA_TYPES:
        body = event.payload.get(event.type)
        body = body if isinstance(body, dict) else {}
        fields.update(
            media_id=str(body.get("id") or "")[:64],
            mime_type=str(body.get("mime_type") or "")[:128],
            file_name=str(body.get("filename") or "")[:255],
        )
    return fields


# --- Delivery statuses --------------------------------------------------------------------------


@receiver(message_status_updated, dispatch_uid="inbox.on_message_status")
def on_message_status(sender, event: MessageStatus, **kwargs) -> None:
    new_status = str(event.status or "").lower()
    if new_status not in STATUS_RANK and new_status != Status.FAILED:
        logger.info("Ignoring unknown message status %r for %s", event.status, event.wamid)
        return
    with transaction.atomic():
        message = _locked_message(event)
        if message is None and _wamid_may_still_arrive(event):
            # Raising makes the webhook task retry the delivery once the wamid is stored.
            raise StatusForUnknownMessage(f"No message with wamid {event.wamid} yet.")
        if message is None:
            message = _locked_message(event)  # a dispatch may have committed in between
        if message is None:
            logger.info("Ignoring %s status for unknown wamid %s", new_status, event.wamid)
            return
        if apply_status(message, new_status, event):
            services.emit_delivery_updated(message, occurred_at=event.timestamp)


def _locked_message(event: MessageStatus) -> Message | None:
    return (
        Message.objects.select_for_update()
        .filter(workspace_id=event.workspace_id, wamid=event.wamid)
        .first()
    )


def _wamid_may_still_arrive(event: MessageStatus) -> bool:
    """The wamid is stored in the same update that moves a message from sending to sent, so a
    status can only precede its message while one is still sending on that number. Statuses for
    messages sent elsewhere (another tool on the same number, pre-UpChatz history) are ignored."""
    if timezone.now() - event.timestamp >= UNKNOWN_WAMID_RETRY_WINDOW:
        return False
    return Message.objects.filter(
        workspace_id=event.workspace_id,
        status=Message.Status.SENDING,
        conversation__phone_number__phone_number_id=event.phone_number_id,
    ).exists()


def _target_status(current: str, new: str) -> str:
    """Monotonic progression: sent < delivered < read. ``failed`` beats queued/sending/sent and a
    later delivered/read beats ``failed``."""
    if new == Status.FAILED:
        return current if current in (Status.DELIVERED, Status.READ) else Status.FAILED
    if current == Status.FAILED:
        return new if new in (Status.DELIVERED, Status.READ) else current
    if current not in STATUS_RANK:  # queued/sending
        return new
    return new if STATUS_RANK[new] > STATUS_RANK[current] else current


def apply_status(message: Message, new_status: str, event: MessageStatus) -> bool:
    """Apply a webhook status to a locked outbound message. Returns True if the status changed."""
    if message.direction != Message.Direction.OUTBOUND or message.status == Status.RECEIVED:
        return False
    current = message.status
    target = _target_status(current, new_status)
    timestamp = event.timestamp
    updates: dict = {}

    def set_once(field: str) -> None:
        if getattr(message, field) is None:
            updates[field] = timestamp

    if new_status in STATUS_RANK:
        set_once("sent_at")
        if new_status in (Status.DELIVERED, Status.READ):
            set_once("delivered_at")
        if new_status == Status.READ:
            set_once("read_at")
    if target != current:
        updates["status"] = target
        if target == Status.FAILED:
            error = event.errors[0] if event.errors else None
            updates["failed_at"] = timestamp
            updates["error_code"] = str(error.code) if error else ""
            updates["error_message"] = (
                (error.details or error.message or error.title)[:1000] if error else ""
            )
        elif current == Status.FAILED:
            updates.update(failed_at=None, error_code="", error_message="")
    if event.pricing_category and event.pricing_category != message.pricing_category:
        updates["pricing_category"] = event.pricing_category[:32]
    if event.billable is not None and event.billable != message.billable:
        updates["billable"] = event.billable

    if updates:
        for field, value in updates.items():
            setattr(message, field, value)
        message.save(update_fields=[*updates, "updated_at"])
    return target != current
