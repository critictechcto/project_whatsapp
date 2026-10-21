"""Razorpay and Cashfree webhook processing.

Razorpay: the view verifies the signature; :func:`handle_delivery` deduplicates on the event id
and applies the event in one transaction. If processing raises, the event row rolls back too, the
view returns 500 and Razorpay retries. ``subscription.*`` events drive auto-pay subscriptions;
``order.paid`` fulfils a one-time (prepaid) order, idempotently, like verify does.

Cashfree: :func:`handle_cashfree_event` fulfils a paid billing order; ``services.fulfil_order``
locks the order, so a retry or a race with verify issues one invoice.
"""

import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from . import entitlements, services
from .invoices import INDIA_TZ
from .models import BillingOrder, BillingProvider, RazorpayEvent, Subscription

logger = logging.getLogger(__name__)

Status = Subscription.Status
Handler = Callable[[Subscription, dict, Mapping[str, Any]], None]


def handle_delivery(event_id: str, payload: Mapping[str, Any]) -> str:
    """Process one delivery once. Returns ``duplicate``, ``processed``, ``ignored``, ``logged``
    or ``unknown_subscription`` (``duplicate`` too for an order another event already paid)."""
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
        order_id = payment.get("order_id")
        if isinstance(order_id, str) and order_id:
            order = BillingOrder.objects.filter(
                provider=BillingProvider.RAZORPAY, order_id=order_id
            ).first()
            if order is not None:
                logger.warning(
                    "Payment for billing order %s (workspace %s) failed; the order stays open",
                    order.order_id,
                    order.workspace_id,
                )
        return "logged"

    if event_type == "order.paid":
        return _order_paid(payload)

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


def _order_paid(payload: Mapping[str, Any]) -> str:
    """``order.paid`` for a one-time (prepaid) billing order: fulfil it once."""
    entity = _entity(payload, "order")
    order_id = entity.get("id")
    order = (
        BillingOrder.objects.filter(provider=BillingProvider.RAZORPAY, order_id=order_id).first()
        if isinstance(order_id, str) and order_id
        else None
    )
    if order is None:
        logger.info("Razorpay order.paid for an unknown order %r ignored", order_id)
        return "ignored"
    amount = entity.get("amount")
    if isinstance(amount, bool) or amount != order.amount_paise:
        logger.warning(
            "Razorpay order %s was paid %r paise, expected %s; ignored",
            order.order_id,
            amount,
            order.amount_paise,
        )
        return "ignored"
    payment = _entity(payload, "payment")
    payment_id = str(payment.get("id") or "")[:64] or order.order_id
    fulfilled = services.fulfil_order(
        order.order_id,
        payment_id=payment_id,
        paid_at=services.timestamp_to_datetime(payment.get("created_at")),
    )
    return "processed" if fulfilled else "duplicate"


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


# --- Cashfree (prepaid orders) --------------------------------------------------------------

CASHFREE_SUCCESS = "PAYMENT_SUCCESS_WEBHOOK"
CASHFREE_LOGGED = frozenset({"PAYMENT_FAILED_WEBHOOK", "PAYMENT_USER_DROPPED_WEBHOOK"})


def handle_cashfree_event(payload: Mapping[str, Any]) -> str:
    """Apply one signed Cashfree payment webhook. Returns ``processed``, ``duplicate``,
    ``logged`` or ``ignored``. Raising makes the view answer 500 and Cashfree retry."""
    event_type = payload.get("type")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    order_id = order.get("order_id")
    if event_type in CASHFREE_LOGGED:
        logger.info(
            "Cashfree %s for order %s (payment status %s)",
            event_type,
            order_id,
            payment.get("payment_status"),
        )
        return "logged"
    if event_type != CASHFREE_SUCCESS or payment.get("payment_status") != "SUCCESS":
        logger.info("Cashfree event %r not handled", event_type)
        return "ignored"

    billing_order = (
        BillingOrder.objects.filter(order_id=order_id).first()
        if isinstance(order_id, str) and order_id
        else None
    )
    if billing_order is None:
        logger.info("Cashfree payment for an unknown order %r ignored", order_id)
        return "ignored"
    amount = services.rupees_to_paise(order.get("order_amount"))
    if amount != billing_order.amount_paise:
        logger.warning(
            "Cashfree payment for order %s was %s paise, expected %s; ignored",
            order_id,
            amount,
            billing_order.amount_paise,
        )
        return "ignored"
    payment_id = str(payment.get("cf_payment_id") or "")[:64] or billing_order.order_id
    fulfilled = services.fulfil_order(
        billing_order.order_id, payment_id=payment_id, paid_at=_parse_time(payment)
    )
    return "processed" if fulfilled else "duplicate"


def _parse_time(payment: Mapping[str, Any]) -> datetime | None:
    value = payment.get("payment_time")
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=INDIA_TZ)


SUBSCRIPTION_HANDLERS: dict[str, Handler] = {
    "subscription.authenticated": _activated,
    "subscription.activated": _activated,
    "subscription.charged": _charged,
    "subscription.pending": _set_status(Status.PENDING),
    "subscription.halted": _set_status(Status.HALTED),
    "subscription.cancelled": _ended,
    "subscription.completed": _ended,
}
