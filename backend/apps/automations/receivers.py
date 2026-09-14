"""Queue automation processing for inbound messages the inbox stored."""

from functools import partial

from django.db import transaction
from django.dispatch import receiver

from common.commerce import is_claimed_by_commerce
from common.events import MessageRecorded, message_recorded

from .tasks import process_inbound

INBOUND = "inbound"


@receiver(message_recorded, dispatch_uid="automations.on_message_recorded")
def on_message_recorded(sender, event: MessageRecorded, **kwargs) -> None:
    """Only customer messages trigger automations. Outbound messages, including the ones
    automations send themselves, are ignored so rules can't loop. Messages commerce answers
    (carts, ``upc:`` replies, store keywords) are skipped so a buyer never gets two replies; no
    run is recorded. Redelivered events are safe: the task records one run per (rule, message)."""
    if event.direction != INBOUND or event.source != INBOUND:
        return
    if is_claimed_by_commerce(event):
        return
    transaction.on_commit(
        partial(
            process_inbound.delay,
            str(event.message_id),
            is_first_inbound=event.is_first_inbound,
            contact_created=event.contact_created,
        )
    )
