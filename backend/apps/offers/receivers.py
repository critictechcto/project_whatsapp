"""Offers receivers and the commerce claimer.

- Claimer: inbound text that is exactly a live offer code is answered by offers, so automations
  skip it.
- ``MessageRecorded`` (inbound offer code): queue ``offers.handle_code_message`` on commit; the
  task is idempotent on the wamid because webhook retries re-emit events.
- ``OrderStatusChanged``: cancelled/expired orders put their claim back to ``claimed``; delivered
  and paid (or completed) orders redeem it. Both only touch ``applied`` claims, so repeats are
  no-ops.
"""

from functools import partial

from django.db import transaction
from django.dispatch import receiver

from common.commerce import register_message_claimer
from common.events import (
    MessageRecorded,
    OrderStatusChanged,
    message_recorded,
    order_status_changed,
)

from . import services, tasks

RELEASE_STATUSES = frozenset({"cancelled", "expired"})
PAID_STATUSES = frozenset({"paid", "cod_collected"})

register_message_claimer(services.is_offer_message)


@receiver(message_recorded, dispatch_uid="offers.on_message_recorded")
def on_message_recorded(sender, event: MessageRecorded, **kwargs) -> None:
    if not services.is_offer_message(event):
        return
    transaction.on_commit(
        partial(tasks.handle_code_message.delay, str(event.message_id)), robust=True
    )


@receiver(order_status_changed, dispatch_uid="offers.on_order_status_changed")
def on_order_status_changed(sender, event: OrderStatusChanged, **kwargs) -> None:
    if event.new_status in RELEASE_STATUSES:
        services.release_for_order_id(event.workspace_id, event.order_id)
    elif event.new_status == "completed" or (
        event.new_status == "delivered" and event.payment_status in PAID_STATUSES
    ):
        services.redeem_for_order_id(
            event.workspace_id, event.order_id, bill_paise=event.total_paise
        )
