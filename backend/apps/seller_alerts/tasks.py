"""Seller alerts Celery tasks."""

import logging

from celery import shared_task
from django.db import transaction

from apps.orders.models import Order

from . import services
from .models import AlertMessage, AlertRecipient
from .platform import platform_alerts_available

logger = logging.getLogger(__name__)

MAX_SEND_RETRIES = 3
SEND_RETRY_COUNTDOWNS = (10, 60, 300)


@shared_task(bind=True, name="seller_alerts.send_alert", max_retries=MAX_SEND_RETRIES)
def send_alert(
    self, recipient_id: str, order_id: str, event: str, new_status: str, actor: str = ""
) -> str:
    """Send one order alert to one recipient. Idempotent on (recipient, order, event, status):
    the ``AlertMessage`` row is created once and sent only while it is queued."""
    if not platform_alerts_available():
        return "unavailable"
    final = self.request.retries >= self.max_retries
    with transaction.atomic():
        recipient = (
            AlertRecipient.objects.select_related("workspace").filter(pk=recipient_id).first()
        )
        if (
            recipient is None
            or recipient.status != AlertRecipient.Status.VERIFIED
            or event not in (recipient.events or [])
        ):
            return "skipped"
        order = (
            Order.objects.select_related("workspace")
            .filter(pk=order_id, workspace_id=recipient.workspace_id)
            .first()
        )
        if order is None:
            return "skipped"
        key = services.alert_dedupe_key(recipient.pk, order.pk, event, new_status)
        AlertMessage.objects.bulk_create(
            [
                AlertMessage(
                    recipient=recipient,
                    workspace_id=recipient.workspace_id,
                    order=order,
                    kind=event,
                    to_wa_id=recipient.wa_id,
                    dedupe_key=key,
                )
            ],
            ignore_conflicts=True,
        )
        message = AlertMessage.objects.select_for_update().get(dedupe_key=key)
        if message.status != AlertMessage.Status.QUEUED:
            return "duplicate"
        outbound = services.build_alert(order, event, actor=actor)
        delivery = services.deliver(recipient, outbound, order=order, message=message, final=final)

    if delivery.error is not None and delivery.error.retryable and not final:
        countdown = SEND_RETRY_COUNTDOWNS[min(self.request.retries, len(SEND_RETRY_COUNTDOWNS) - 1)]
        raise self.retry(exc=delivery.error, countdown=countdown)
    return delivery.message.status
