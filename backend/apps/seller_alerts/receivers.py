"""Seller alerts react to order status changes and to messages sent to the alerts number."""

from functools import partial

from django.db import transaction
from django.dispatch import receiver

from common.events import (
    OrderStatusChanged,
    PlatformInboundMessage,
    order_status_changed,
    platform_inbound_message_received,
)

from . import inbound, services, tasks
from .models import AlertRecipient
from .platform import platform_alerts_available


@receiver(order_status_changed, dispatch_uid="seller_alerts.queue_order_alerts")
def queue_order_alerts(sender, event: OrderStatusChanged, **kwargs) -> None:
    """Queue ``seller_alerts.send_alert`` for every verified recipient subscribed to the alert.
    Re-emitted events are harmless: the task sends each (recipient, order, event, status) once."""
    alert_event = services.alert_event_for(event)
    if alert_event is None or not platform_alerts_available():
        return
    recipient_ids = AlertRecipient.objects.filter(
        workspace_id=event.workspace_id,
        status=AlertRecipient.Status.VERIFIED,
        events__contains=[alert_event],
    ).values_list("pk", flat=True)
    for recipient_id in recipient_ids:
        send = partial(
            tasks.send_alert.delay,
            str(recipient_id),
            str(event.order_id),
            alert_event,
            event.new_status,
            event.actor,
        )
        transaction.on_commit(send, robust=True)


@receiver(platform_inbound_message_received, dispatch_uid="seller_alerts.handle_platform_inbound")
def handle_platform_inbound(sender, event: PlatformInboundMessage, **kwargs) -> None:
    inbound.handle_inbound(event)
