"""Order state changes shared by checkout, payment events and the merchant actions.

Every status or payment-status change writes an :class:`OrderEvent`, emits
``OrderStatusChanged`` on commit and sends an ``order.updated`` realtime frame. Callers lock the
order row (:func:`lock_order`) before changing it.
"""

import logging
from collections.abc import Iterable
from functools import partial

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog import services as catalog_services
from apps.payments import services as payment_services
from apps.payments.exceptions import (
    PaymentAccountInvalid,
    PaymentAccountMissing,
    PaymentProviderError,
)
from common import events, realtime
from common.exceptions import Conflict

from . import notifications, transitions
from .models import Order, OrderEvent

logger = logging.getLogger(__name__)

Status = Order.Status
Actor = OrderEvent.Actor

STATUS_TIMESTAMPS = {
    Status.CONFIRMED: "confirmed_at",
    Status.PACKED: "packed_at",
    Status.SHIPPED: "shipped_at",
    Status.DELIVERED: "delivered_at",
    Status.CANCELLED: "cancelled_at",
    Status.EXPIRED: "expired_at",
}
OPEN_LINK_STATUSES = ("creating", "created")


def lock_order(order_id, *, workspace_id=None) -> Order | None:
    """The order row locked for update (``None`` when it doesn't exist)."""
    queryset = Order.objects.select_for_update(of=("self",)).select_related(
        "workspace", "contact", "phone_number__waba", "conversation"
    )
    if workspace_id is not None:
        queryset = queryset.filter(workspace_id=workspace_id)
    return queryset.filter(pk=order_id).first()


def record_event(
    order: Order,
    type: str,
    *,
    actor: str,
    user=None,
    detail: str = "",
    from_status: str = "",
    to_status: str = "",
    message=None,
    metadata: dict | None = None,
) -> OrderEvent:
    return OrderEvent.objects.create(
        workspace_id=order.workspace_id,
        order=order,
        type=type,
        actor=actor,
        user=user,
        detail=detail,
        from_status=from_status,
        to_status=to_status,
        message=message,
        metadata=metadata or {},
    )


def emit_status_changed(order: Order, old_status: str, *, actor: str, user=None) -> None:
    event = events.OrderStatusChanged(
        workspace_id=order.workspace_id,
        order_id=order.pk,
        order_number=order.number,
        contact_id=order.contact_id,
        phone_number_id=order.phone_number_id,
        old_status=old_status,
        new_status=order.status,
        payment_status=order.payment_status,
        payment_method=order.payment_method,
        total_paise=order.total_paise,
        actor=actor,
        actor_user_id=getattr(user, "pk", None),
        occurred_at=timezone.now(),
    )
    transaction.on_commit(partial(events.emit, events.order_status_changed, event))


def broadcast_created(order: Order) -> None:
    realtime.broadcast(
        order.workspace_id,
        "order.created",
        {"order_id": order.pk, "number": order.number, "status": order.status},
    )


def broadcast_updated(order: Order) -> None:
    realtime.broadcast(
        order.workspace_id,
        "order.updated",
        {"order_id": order.pk, "status": order.status, "payment_status": order.payment_status},
    )


def set_status(
    order: Order,
    to_status: str,
    *,
    actor: str,
    user=None,
    system: bool = False,
    force: bool = False,
    detail: str = "",
    message=None,
) -> str:
    """Move a locked order to ``to_status``; returns the old status.

    ``system`` allows the system-only moves of the transition table; ``force`` skips the table
    (a payment arriving for an expired or cancelled checkout).
    """
    old_status = order.status
    if not force:
        transitions.check_transition(old_status, to_status, system=system)
    now = timezone.now()
    order.status = to_status
    if stamp := STATUS_TIMESTAMPS.get(to_status):
        setattr(order, stamp, now)
    if to_status not in transitions.CHECKOUT_STATUSES:
        order.expires_at = None
    order.save()
    record_event(
        order,
        OrderEvent.Type.STATUS_CHANGED,
        actor=actor,
        user=user,
        detail=detail,
        from_status=old_status,
        to_status=to_status,
        message=message,
    )
    emit_status_changed(order, old_status, actor=actor, user=user)
    broadcast_updated(order)
    return old_status


def payment_changed(order: Order, *, actor: str, user=None) -> None:
    """Emit and broadcast a payment-status change that kept the order status."""
    emit_status_changed(order, order.status, actor=actor, user=user)
    broadcast_updated(order)


# --- Stock and payment links ------------------------------------------------------------------


def stock_lines(order: Order) -> list[tuple]:
    return [
        (item.product_id, item.quantity)
        for item in order.items.all()
        if item.product_id is not None and item.quantity > 0
    ]


def reserve_stock(order: Order) -> None:
    """Reserve the order's stock (all or nothing); raises ``OutOfStock``."""
    if order.stock_reserved:
        return
    catalog_services.reserve_stock(order.workspace, stock_lines(order))
    order.stock_reserved = True
    order.save(update_fields=["stock_reserved", "updated_at"])


def release_stock(order: Order, *, actor: str, user=None, detail: str = "") -> bool:
    if not order.stock_reserved:
        return False
    catalog_services.release_stock(order.workspace, stock_lines(order))
    order.stock_reserved = False
    order.save(update_fields=["stock_reserved", "updated_at"])
    record_event(
        order,
        OrderEvent.Type.STOCK_RELEASED,
        actor=actor,
        user=user,
        detail=detail or "Reserved stock was released.",
    )
    return True


def open_payment_links(order: Order) -> list:
    return list(order.payment_links.filter(status__in=OPEN_LINK_STATUSES).order_by("created_at"))


def latest_payment_link(order: Order):
    return order.payment_links.order_by("-created_at", "-pk").first()


def cancel_payment_links(order_id) -> list:
    """Cancel the order's open payment links on the gateway; returns the resulting links.

    Failures are logged: a link that stays open and gets paid later is handled by the payment
    receivers (the order is revived or flagged ``needs_attention``).
    """
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return []
    results = []
    for link in open_payment_links(order):
        try:
            results.append(payment_services.cancel_payment_link(link))
        except (PaymentProviderError, PaymentAccountMissing, PaymentAccountInvalid) as exc:
            logger.warning("Payment link %s of order %s not cancelled: %s", link.pk, order_id, exc)
            results.append(None)
    return results


def cancel_payment_links_on_commit(order: Order) -> None:
    transaction.on_commit(partial(cancel_payment_links, order.pk), robust=True)


# --- Merchant actions ---------------------------------------------------------------------------


def _locked(order: Order) -> Order:
    locked = lock_order(order.pk, workspace_id=order.workspace_id)
    if locked is None:
        raise Order.DoesNotExist(f"Order {order.pk} no longer exists.")
    return locked


def transition(
    order: Order,
    to_status: str,
    *,
    actor: str,
    user=None,
    courier_name: str = "",
    awb_number: str = "",
    tracking_url: str = "",
    notify_buyer: bool = True,
) -> Order:
    if to_status == Status.CANCELLED:
        return cancel_order(order, actor=actor, user=user, notify_buyer=notify_buyer)
    courier_name, awb_number = (courier_name or "").strip(), (awb_number or "").strip()
    tracking_url = (tracking_url or "").strip()
    if to_status == Status.SHIPPED:
        errors = {
            field: ["Required when marking an order shipped."]
            for field, value in (("courier_name", courier_name), ("awb_number", awb_number))
            if not value
        }
        if tracking_url and not tracking_url.lower().startswith("https://"):
            errors["tracking_url"] = ["Use an https:// link."]
        if errors:
            raise ValidationError(errors)
    with transaction.atomic():
        order = _locked(order)
        transitions.check_transition(order.status, to_status)
        if to_status == Status.SHIPPED:
            order.courier_name = courier_name[:100]
            order.awb_number = awb_number[:64]
            order.tracking_url = tracking_url[:500]
        set_status(order, to_status, actor=actor, user=user)
        if notify_buyer and to_status in notifications.NOTIFIED_STATUSES:
            notifications.notify_buyer(order, to_status, actor=actor, user=user)
    return order


def cancel_order(
    order: Order,
    *,
    actor: str,
    user=None,
    reason: str = "",
    restock: bool = True,
    notify_buyer: bool = True,
    system: bool = False,
) -> Order:
    with transaction.atomic():
        order = _locked(order)
        transitions.check_transition(order.status, Status.CANCELLED, system=system)
        if order.stock_reserved:
            if restock:
                release_stock(order, actor=actor, user=user, detail="Stock returned on cancel.")
            else:
                order.stock_reserved = False
        order.cancel_reason = (reason or "").strip()[:200]
        set_status(order, Status.CANCELLED, actor=actor, user=user, system=system, detail=reason)
        cancel_payment_links_on_commit(order)
        if notify_buyer:
            notifications.notify_buyer(order, Status.CANCELLED, actor=actor, user=user)
    return order


def mark_cod_collected(order: Order, *, actor: str, user=None) -> Order:
    with transaction.atomic():
        order = _locked(order)
        if (
            order.payment_method != Order.PaymentMethod.COD
            or order.payment_status != Order.PaymentStatus.COD_PENDING
            or order.status not in (Status.SHIPPED, Status.DELIVERED)
        ):
            raise Conflict(
                "Cash can be marked collected only for cash-on-delivery orders that are shipped "
                "or delivered and not yet collected."
            )
        order.payment_status = Order.PaymentStatus.COD_COLLECTED
        order.cod_collected_at = timezone.now()
        order.save()
        record_event(
            order,
            OrderEvent.Type.COD_COLLECTED,
            actor=actor,
            user=user,
            detail="Cash collected on delivery.",
        )
        payment_changed(order, actor=actor, user=user)
    return order


def mark_refunded(order: Order, *, actor: str, user=None) -> Order:
    with transaction.atomic():
        order = _locked(order)
        if order.payment_status != Order.PaymentStatus.PAID or order.status not in (
            Status.CANCELLED,
            Status.NEEDS_ATTENTION,
        ):
            raise Conflict(
                "Only paid orders that are cancelled or need attention can be marked refunded."
            )
        order.payment_status = Order.PaymentStatus.REFUNDED_MANUAL
        order.refunded_at = timezone.now()
        order.save()
        record_event(
            order,
            OrderEvent.Type.REFUNDED_MANUAL,
            actor=actor,
            user=user,
            detail="Refund recorded; the refund itself is made in the payment gateway.",
        )
        payment_changed(order, actor=actor, user=user)
    return order


def update_notes(order: Order, notes: str, *, actor: str, user=None) -> Order:
    with transaction.atomic():
        order = _locked(order)
        if order.notes == notes:
            return order
        order.notes = notes
        order.save(update_fields=["notes", "updated_at"])
        record_event(order, OrderEvent.Type.NOTE, actor=actor, user=user, detail="Notes updated.")
        broadcast_updated(order)
    return order


def open_orders_for_workspaces(workspace_ids: Iterable, *, limit: int = 10) -> list[Order]:
    return list(
        Order.objects.filter(
            workspace_id__in=list(workspace_ids), status__in=transitions.OPEN_STATUSES
        )
        .select_related("workspace", "contact", "phone_number")
        .order_by("-created_at", "-pk")[: max(int(limit), 0)]
    )
