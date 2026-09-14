"""Shop receivers, the commerce claimer and the automation action hooks.

- ``MessageRecorded`` (inbound, enabled store): queue ``shop.handle_inbound``, which is idempotent
  on the wamid because webhook retries re-emit events.
- ``OrderStatusChanged`` (checkout → ``confirmed``): empty the buyer's bot cart.
"""

from functools import partial

from django.db import transaction
from django.dispatch import receiver

from apps.automations.hooks import register_commerce_action
from apps.orders.models import Order
from common.commerce import register_message_claimer
from common.events import (
    MessageRecorded,
    OrderStatusChanged,
    message_recorded,
    order_status_changed,
)

from . import actions, services, tasks
from .claims import claim_shop_message

INBOUND = "inbound"

register_message_claimer(claim_shop_message)
for _action_type, _handler in actions.ACTIONS.items():
    register_commerce_action(_action_type, _handler)


@receiver(message_recorded, dispatch_uid="shop.on_message_recorded")
def on_message_recorded(sender, event: MessageRecorded, **kwargs) -> None:
    if event.direction != INBOUND or event.source != INBOUND:
        return
    if services.enabled_store(event.workspace_id) is None:
        return
    transaction.on_commit(
        partial(tasks.handle_inbound.delay, str(event.message_id), event.reply_id), robust=True
    )


@receiver(order_status_changed, dispatch_uid="shop.on_order_status_changed")
def on_order_status_changed(sender, event: OrderStatusChanged, **kwargs) -> None:
    if (
        event.new_status != Order.Status.CONFIRMED
        or event.old_status not in Order.CHECKOUT_STATUSES
    ):
        return
    services.clear_cart_after_order(
        workspace_id=event.workspace_id,
        contact_id=event.contact_id,
        phone_number_id=event.phone_number_id,
    )
