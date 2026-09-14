"""React to WhatsApp webhook events. Every handler is idempotent (deliveries can repeat)."""

import logging

from django.dispatch import receiver

from apps.tenants.models import Workspace
from common.events import (
    InboundMessage,
    MessageStatus,
    inbound_message_received,
    message_status_updated,
)
from common.phone import InvalidPhoneNumber

from . import services
from .models import ConsentEvent

logger = logging.getLogger(__name__)

# Meta: the user has stopped marketing messages from this business.
META_MARKETING_OPTOUT_ERROR = 131050


def _workspace(workspace_id) -> Workspace | None:
    return Workspace.objects.filter(pk=workspace_id).first()


@receiver(inbound_message_received, dispatch_uid="contacts.on_inbound_message")
def on_inbound_message(sender, event: InboundMessage, **kwargs) -> None:
    workspace = _workspace(event.workspace_id)
    if workspace is None:
        return
    try:
        contact = services.get_or_create_from_wa(
            workspace, event.from_wa_id, profile_name=event.profile_name
        )
    except InvalidPhoneNumber:
        logger.warning("Ignoring inbound message %s with invalid wa_id", event.wamid)
        return
    services.touch_last_inbound(contact, event.timestamp)

    action = services.match_consent_keyword(event.text)
    if action is None:
        return
    record = (
        services.record_opt_out if action == ConsentEvent.Action.OPT_OUT else services.record_opt_in
    )
    record(
        contact,
        source=ConsentEvent.Source.WHATSAPP_KEYWORD,
        evidence=f"Customer sent {event.text.strip()!r} on WhatsApp.",
        wamid=event.wamid,
        occurred_at=event.timestamp,
    )


@receiver(message_status_updated, dispatch_uid="contacts.on_message_status")
def on_message_status(sender, event: MessageStatus, **kwargs) -> None:
    if META_MARKETING_OPTOUT_ERROR not in event.error_codes:
        return
    workspace = _workspace(event.workspace_id)
    if workspace is None:
        return
    try:
        contact = services.get_or_create_from_wa(workspace, event.recipient_wa_id)
    except InvalidPhoneNumber:
        logger.warning("Ignoring status for %s with invalid recipient wa_id", event.wamid)
        return
    services.record_opt_out(
        contact,
        source=ConsentEvent.Source.META_MARKETING_OPTOUT,
        evidence=(
            f"Meta rejected message {event.wamid} with error {META_MARKETING_OPTOUT_ERROR}: "
            "the user stopped marketing messages from this business."
        ),
        wamid=event.wamid,
        occurred_at=event.timestamp,
    )
