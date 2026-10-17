"""Order state changes shared by checkout, payment events and the merchant actions.

Every status or payment-status change writes an :class:`OrderEvent`, emits
``OrderStatusChanged`` on commit and sends an ``order.updated`` realtime frame. Callers lock the
order row (:func:`lock_order`) before changing it.
"""

import logging
from collections.abc import Iterable
from datetime import datetime, time, timedelta
from functools import partial

from django.db import transaction
from django.db.models import Q
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

from . import booking, notifications, transitions
from .exceptions import InvalidOrderTransition
from .models import Order, OrderEvent, StoreSettings

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
    event = OrderEvent.objects.create(
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
    # Events written in the same clock tick would share ``created_at`` and the timeline would
    # tie-break on random UUIDs; keep each order's events strictly increasing instead.
    previous = (
        order.events.exclude(pk=event.pk)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if previous is not None and event.created_at <= previous:
        event.created_at = previous + timedelta(microseconds=1)
        OrderEvent.objects.filter(pk=event.pk).update(created_at=event.created_at)
    return event


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
        transitions.check_transition(old_status, to_status, kind=order.kind, system=system)
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
    # Tracking details are optional: small sellers often deliver themselves or have no AWB.
    if (
        to_status == Status.SHIPPED
        and tracking_url
        and not tracking_url.lower().startswith("https://")
    ):
        raise ValidationError({"tracking_url": ["Use an https:// link."]})
    with transaction.atomic():
        order = _locked(order)
        transitions.check_transition(order.status, to_status, kind=order.kind)
        if order.is_booking and to_status == Status.CONFIRMED and order.appointment_at is None:
            raise InvalidOrderTransition(
                order.status,
                to_status,
                allowed=order.allowed_transitions,
                detail="Set the appointment time to confirm a booking (confirm-booking).",
            )
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
        transitions.check_transition(order.status, Status.CANCELLED, kind=order.kind, system=system)
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
        at_shop = order.payment_method == Order.PaymentMethod.PAY_AT_SHOP
        if order.payment_status != Order.PaymentStatus.COD_PENDING or not (
            (
                order.payment_method == Order.PaymentMethod.COD
                and order.status in (Status.SHIPPED, Status.DELIVERED)
            )
            or (at_shop and order.status in (Status.CONFIRMED, Status.COMPLETED))
        ):
            raise InvalidOrderTransition(
                order.status,
                Order.PaymentStatus.COD_COLLECTED,
                allowed=order.allowed_transitions,
                detail=(
                    "Payment can be marked collected only for cash-on-delivery orders that are "
                    "shipped or delivered, or pay-at-shop bookings that are confirmed or "
                    "completed, and not yet collected."
                ),
            )
        order.payment_status = Order.PaymentStatus.COD_COLLECTED
        order.cod_collected_at = timezone.now()
        order.save()
        record_event(
            order,
            OrderEvent.Type.COD_COLLECTED,
            actor=actor,
            user=user,
            detail="Paid at the shop." if at_shop else "Cash collected on delivery.",
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
            raise InvalidOrderTransition(
                order.status,
                Order.PaymentStatus.REFUNDED_MANUAL,
                allowed=order.allowed_transitions,
                detail=(
                    "Only paid orders that are cancelled or need attention can be marked refunded."
                ),
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


def confirm_booking(order: Order, *, appointment_at, actor: str, user=None) -> Order:
    """Confirm a requested booking at ``appointment_at``, or move a confirmed one
    (docs/contracts/services-and-offers.md, "Merchant API").

    Sets ``appointment_at`` and clears both reminders (sent again for the new time), the buyer's
    attendance answer and a pending reschedule request, records ``appointment_set`` and
    notifies the buyer. A naive ``appointment_at`` is workspace time. Raises
    :class:`InvalidOrderTransition` (409) for anything but a ``requested`` or ``confirmed``
    booking.
    """
    with transaction.atomic():
        order = _locked(order)
        if not order.is_booking or order.status not in (Status.REQUESTED, Status.CONFIRMED):
            raise InvalidOrderTransition(
                order.status,
                Status.CONFIRMED,
                allowed=order.allowed_transitions,
                detail="Only requested or confirmed bookings can be given an appointment time.",
            )
        if timezone.is_naive(appointment_at):
            appointment_at = timezone.make_aware(
                appointment_at, booking.workspace_zone(order.workspace)
            )
        rescheduled = order.status == Status.CONFIRMED
        if rescheduled and order.appointment_at == appointment_at:
            return order
        order.appointment_at = appointment_at
        order.reminder_sent_at = None
        order.day_before_reminder_sent_at = None
        order.reschedule_requested_at = None
        order.attendance_confirmed_at = None
        when = booking.format_moment(appointment_at, order.workspace)
        record_event(
            order,
            OrderEvent.Type.APPOINTMENT_SET,
            actor=actor,
            user=user,
            detail=f"Appointment moved to {when}."
            if rescheduled
            else f"Appointment set for {when}.",
            metadata={"appointment_at": appointment_at.isoformat()},
        )
        if rescheduled:
            order.save()
            broadcast_updated(order)
            notifications.notify_buyer(order, "booking_rescheduled", actor=actor, user=user)
        else:
            set_status(order, Status.CONFIRMED, actor=actor, user=user)
            notifications.notify_buyer(order, Status.CONFIRMED, actor=actor, user=user)
    return order


# --- Booking reminders --------------------------------------------------------------------------

MAX_REMINDER_HOURS = 48
DEFAULT_REMINDER_HOURS = 3
DAY_BEFORE_AT = time(18, 0)  # workspace time, the day before the appointment
# The day-before reminder is skipped when the time was set less than this before 18:00.
DAY_BEFORE_MIN_NOTICE = timedelta(hours=12)


def day_before_moment(order: Order):
    """18:00 workspace time on the day before ``appointment_at``."""
    tz = booking.workspace_zone(order.workspace)
    day = order.appointment_at.astimezone(tz).date() - timedelta(days=1)
    return datetime.combine(day, DAY_BEFORE_AT, tzinfo=tz)


def _appointment_set_at(order: Order):
    last = (
        order.events.filter(type=OrderEvent.Type.APPOINTMENT_SET)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return last or order.confirmed_at or order.created_at


def due_reminder(order: Order, store_settings, now) -> str | None:
    """``booking_reminder``, ``booking_day_before`` or None for a locked confirmed booking.

    The hours-before reminder wins when both are due (a late run sends one message).
    """
    if order.appointment_at is None or order.appointment_at <= now:
        return None
    hours = store_settings.booking_reminder_hours if store_settings else DEFAULT_REMINDER_HOURS
    if (
        hours
        and order.reminder_sent_at is None
        and order.appointment_at - now <= timedelta(hours=hours)
    ):
        return "booking_reminder"
    enabled = store_settings.booking_day_before_reminder if store_settings else True
    if not enabled or order.day_before_reminder_sent_at is not None:
        return None
    moment = day_before_moment(order)
    tz = booking.workspace_zone(order.workspace)
    appointment_day = datetime.combine(
        order.appointment_at.astimezone(tz).date(), time.min, tzinfo=tz
    )
    if now < moment or now >= appointment_day:
        return None
    if _appointment_set_at(order) > moment - DAY_BEFORE_MIN_NOTICE:
        return None
    return "booking_day_before"


REMINDER_FIELDS = {
    "booking_reminder": "reminder_sent_at",
    "booking_day_before": "day_before_reminder_sent_at",
}


def send_booking_reminders(*, now=None, batch_size: int = 500) -> int:
    """Remind buyers of confirmed bookings (beat ``orders.send_booking_reminders``): at 18:00 the
    day before (``booking_day_before_reminder``) and ``booking_reminder_hours`` before, each once
    per appointment (``day_before_reminder_sent_at`` / ``reminder_sent_at``; a new time clears
    both). Paid bookings are reminded too; pay-at-shop ones are told what to pay."""
    now = now or timezone.now()
    due = list(
        Order.objects.filter(
            kind=Order.Kind.BOOKING,
            status=Status.CONFIRMED,
            appointment_at__gt=now,
            appointment_at__lte=now + timedelta(hours=MAX_REMINDER_HOURS),
        )
        .filter(Q(reminder_sent_at__isnull=True) | Q(day_before_reminder_sent_at__isnull=True))
        .order_by("appointment_at")
        .values_list("pk", "workspace_id")[:batch_size]
    )
    store_settings = {
        item.workspace_id: item
        for item in StoreSettings.objects.filter(
            workspace_id__in={workspace_id for _, workspace_id in due}
        )
    }
    sent = 0
    for order_id, workspace_id in due:
        with transaction.atomic():
            order = lock_order(order_id)
            if order is None or order.status != Status.CONFIRMED:
                continue
            notification = due_reminder(order, store_settings.get(workspace_id), now)
            if notification is None:
                continue
            setattr(order, REMINDER_FIELDS[notification], now)
            order.save(update_fields=[REMINDER_FIELDS[notification], "updated_at"])
            label = "Day-before reminder" if notification == "booking_day_before" else "Reminder"
            record_event(
                order,
                OrderEvent.Type.REMINDER_SENT,
                actor=Actor.SYSTEM,
                detail=f"{label} for the appointment at "
                f"{booking.format_moment(order.appointment_at, order.workspace)}.",
                metadata={"reminder": notification},
            )
            notifications.notify_buyer(order, notification, actor=Actor.SYSTEM)
        sent += 1
    return sent
