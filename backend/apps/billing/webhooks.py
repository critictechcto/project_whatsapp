"""Razorpay webhook processing.

The view verifies the signature; :func:`handle_delivery` deduplicates on the event id and applies
the event in one transaction. If processing raises, the event row rolls back too, the view
returns 500 and Razorpay retries.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

from django.db import transaction
from django.utils import timezone

from . import entitlements, services
from .models import RazorpayEvent, Subscription

logger = logging.getLogger(__name__)

Status = Subscription.Status
Handler = Callable[[Subscription, dict, Mapping[str, Any]], None]


def handle_delivery(event_id: str, payload: Mapping[str, Any]) -> str:
    """Process one delivery once. Returns ``duplicate``, ``processed``, ``ignored``, ``logged``
    or ``unknown_subscription``."""
    event_type = payload.get("event")
    event_type = event_type[:64] if isinstance(event_type, str) else ""
    with transaction.atomic():
        event, created = RazorpayEvent.objects.get_or_create(
            event_id=event_id, defaults={"type": event_type, "payload": dict(payload)}
        )
        if not created:
            logger.info("Duplicate Razorpay event %s ignored", event_id)
            return "duplicate"
        outcome = process_event(event_type, payload)
        event.processed_at = timezone.now()
        event.save(update_fields=["processed_at", "updated_at"])
    return outcome


def process_event(event_type: str, payload: Mapping[str, Any]) -> str:
    if event_type == "payment.failed":
        payment = _entity(payload, "payment")
        logger.warning(
            "Razorpay payment %s failed (invoice %s, subscription %s, error %s)",
            payment.get("id"),
            payment.get("invoice_id"),
            payment.get("subscription_id"),
            payment.get("error_code"),
        )
        return "logged"

    handler = SUBSCRIPTION_HANDLERS.get(event_type)
    if handler is None:
        logger.info("Razorpay event %r not handled", event_type)
        return "ignored"
    entity = _entity(payload, "subscription")
    razorpay_id = entity.get("id")
    if not isinstance(razorpay_id, str) or not razorpay_id:
        logger.warning("Razorpay %s event without a subscription id", event_type)
        return "ignored"
    subscription = (
        Subscription.objects.select_for_update(of=("self",))
        .select_related("plan", "workspace")
        .filter(razorpay_subscription_id=razorpay_id)
        .first()
    )
    if subscription is None:
        logger.warning("Razorpay %s event for unknown subscription %s", event_type, razorpay_id)
        return "unknown_subscription"
    handler(subscription, entity, payload)
    entitlements.clear_cache(subscription.workspace)
    return "processed"


def _entity(payload: Mapping[str, Any], name: str) -> dict:
    container = payload.get("payload")
    item = container.get(name) if isinstance(container, dict) else None
    entity = item.get("entity") if isinstance(item, dict) else None
    return entity if isinstance(entity, dict) else {}


def _activated(subscription: Subscription, entity: dict, payload: Mapping[str, Any]) -> None:
    services.activate(subscription, entity)


def _charged(subscription: Subscription, entity: dict, payload: Mapping[str, Any]) -> None:
    services.activate(subscription, entity)
    payment = _entity(payload, "payment")
    payment_id = payment.get("id")
    if not isinstance(payment_id, str) or not payment_id:
        logger.warning("subscription.charged for %s without a payment id", subscription.pk)
        return
    issued_at = timezone.now()
    period_start = (
        services.timestamp_to_datetime(entity.get("current_start"))
        or subscription.current_period_start
        or issued_at
    )
    period_end = (
        services.timestamp_to_datetime(entity.get("current_end"))
        or subscription.current_period_end
        or services.period_end_after(period_start, subscription.interval)
    )
    amount = payment.get("amount")
    services.create_paid_invoice(
        subscription=subscription,
        payment_id=payment_id[:64],
        issued_at=issued_at,
        period_start=period_start,
        period_end=period_end,
        razorpay_invoice_id=str(payment.get("invoice_id") or "")[:64],
        amount_paid_paise=amount
        if isinstance(amount, int) and not isinstance(amount, bool)
        else None,
    )


def _set_status(status: str) -> Handler:
    def handler(subscription: Subscription, entity: dict, payload: Mapping[str, Any]) -> None:
        if subscription.status in (Status.CANCELLED, Status.EXPIRED):
            logger.info("Ignoring %s for ended subscription %s", status, subscription.pk)
            return
        subscription.status = status
        services.apply_period(subscription, entity)
        subscription.save()

    return handler


def _ended(subscription: Subscription, entity: dict, payload: Mapping[str, Any]) -> None:
    now = timezone.now()
    if subscription.checkout_in_progress:
        services.abandon_checkout(subscription, keep_trial=True, now=now)
    else:
        services.apply_period(subscription, entity)
        period_end = subscription.current_period_end
        ended = period_end is None or period_end <= now
        subscription.status = Status.EXPIRED if ended else Status.CANCELLED
    subscription.cancel_at_period_end = False
    subscription.save()


SUBSCRIPTION_HANDLERS: dict[str, Handler] = {
    "subscription.authenticated": _activated,
    "subscription.activated": _activated,
    "subscription.charged": _charged,
    "subscription.pending": _set_status(Status.PENDING),
    "subscription.halted": _set_status(Status.HALTED),
    "subscription.cancelled": _ended,
    "subscription.completed": _ended,
}
