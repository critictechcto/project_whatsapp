"""Queue automation processing for inbound messages the inbox stored."""

from functools import partial

from django.db import transaction
from django.dispatch import receiver

from common.events import MessageRecorded, message_recorded

from .tasks import process_inbound

INBOUND = "inbound"


@receiver(message_recorded, dispatch_uid="automations.on_message_recorded")
def on_message_recorded(sender, event: MessageRecorded, **kwargs) -> None:
    """Only customer messages trigger automations. Outbound messages, including the ones
    automations send themselves, are ignored so rules can't loop. Redelivered events are safe:
    the task records one run per (rule, message)."""
    if event.direction != INBOUND or event.source != INBOUND:
        return
    transaction.on_commit(
        partial(
            process_inbound.delay,
            str(event.message_id),
            is_first_inbound=event.is_first_inbound,
            contact_created=event.contact_created,
        )
    )
