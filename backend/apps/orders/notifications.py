"""Buyer notifications on status changes (docs/contracts/wave-3-commerce.md, "Starter templates").

Inside the 24-hour customer service window the buyer gets a session message (text or
interactive). Outside it, the template mapped in ``StoreSettings.notification_templates`` is sent
with body parameters in the contract order. Every attempt writes an ``OrderEvent``:
``notification_sent`` (with the message) or ``notification_failed``.

``payment_reminder`` (checkout ``send_payment_reminders``) carries the open payment link: a *Pay*
URL button in the window, the template's fourth body parameter outside it.

Bookings (docs/contracts/services-and-offers.md) use their own keys: ``booking_confirmed`` (with
the appointment time), ``booking_rescheduled`` (the time changed; same template as confirmed),
``booking_cancelled``, ``booking_reminder`` (hours before) and ``booking_day_before`` (18:00 the
day before; same template as the reminder). ``confirmed``/``cancelled`` of a booking map to them.
Reminders carry *I'll be there* / *Change time* / *Cancel booking* (``ord:attend``,
``ord:resched``, ``ord:bcancel``): reply buttons in the window, the template's QUICK_REPLY buttons
with per-send payloads outside it.
"""

from apps.inbox import interactive, sending
from apps.inbox.models import Message
from apps.message_templates.models import MessageTemplate
from common.commerce import build_reply_id

from . import booking, buyer
from .models import Order, OrderEvent, StoreSettings
from .money import format_inr
from .store import footer_for, get_store_settings

EMPTY_PARAM = "—"
# The shipped template names a courier; without one the parcel goes "with our delivery partner".
NO_COURIER = "our delivery partner"
NOTIFIED_STATUSES = ("confirmed", "packed", "shipped", "delivered", "cancelled")
BOOKING_NOTIFICATIONS = {"confirmed": "booking_confirmed", "cancelled": "booking_cancelled"}
REMINDERS = ("booking_reminder", "booking_day_before")
PAID_BOOKING_NOTE = "Your booking is paid."
PENDING_BOOKING_NOTE = "Payment pending."


def reminder_buttons(order: Order) -> list[tuple[str, str]]:
    """The reminder's answers, in the order of the starter template's QUICK_REPLY buttons."""
    return [
        (build_reply_id("ord", "attend", order.pk), "I'll be there"),
        (build_reply_id("ord", "resched", order.pk), "Change time"),
        (build_reply_id("ord", "bcancel", order.pk), "Cancel booking"),
    ]


def booking_payment_note(order: Order) -> str:
    """The payment line of booking reminders (docs/contracts/booking-payments.md)."""
    status = order.payment_status
    if (
        order.payment_method == Order.PaymentMethod.PAY_AT_SHOP
        and status == Order.PaymentStatus.COD_PENDING
    ):
        return f"Pay at the shop after your service: {format_inr(order.total_paise)}."
    if status == Order.PaymentStatus.ADVANCE_PAID:
        return (
            f"Advance {format_inr(order.amount_paid_paise)} paid. Pay the rest, "
            f"{format_inr(order.balance_due_paise)}, at the shop."
        )
    if status in (Order.PaymentStatus.PAID, Order.PaymentStatus.COD_COLLECTED):
        return PAID_BOOKING_NOTE
    return PENDING_BOOKING_NOTE


def cancelled_payment_text(order: Order) -> str:
    """What a cancelled order or booking says about money already paid online."""
    if order.payment_status == Order.PaymentStatus.PAID:
        return " The store will refund your payment."
    if order.payment_status == Order.PaymentStatus.ADVANCE_PAID:
        return " The store will contact you about your advance."
    return ""


def quick_reply_payloads(template, order: Order) -> dict[int, str]:
    """Per-send payloads for the template's QUICK_REPLY buttons (by button index), matched in
    order to :func:`reminder_buttons`; none when the template has no quick replies."""
    ids = [reply_id for reply_id, _ in reminder_buttons(order)]
    payloads: dict[int, str] = {}
    for component in template.components or []:
        if not isinstance(component, dict) or str(component.get("type", "")).upper() != "BUTTONS":
            continue
        buttons = component.get("buttons") if isinstance(component.get("buttons"), list) else []
        for index, button in enumerate(buttons):
            if (
                isinstance(button, dict)
                and str(button.get("type", "")).upper() == "QUICK_REPLY"
                and len(payloads) < len(ids)
            ):
                payloads[index] = ids[len(payloads)]
        break
    return payloads


def notification_key(order: Order, notification: str) -> str:
    """The notification key for ``order``: bookings use the ``booking_*`` variants."""
    if order.is_booking:
        return BOOKING_NOTIFICATIONS.get(notification, notification)
    return notification


def template_field(notification: str) -> str | None:
    return StoreSettings.NOTIFICATION_TEMPLATE_FIELDS.get(
        notification
    ) or StoreSettings.BOOKING_TEMPLATE_FIELDS.get(notification)


def template_params(order: Order, notification: str, *, payment_url: str = "") -> list[str]:
    """Body parameters of the ``upc_order_*`` starter template for ``notification``."""
    name, number = buyer.buyer_name(order), order.number
    if notification in REMINDERS:
        return [
            name,
            number,
            booking.service_names(order),
            booking.appointment_text(order),
            booking_payment_note(order),
        ]
    if notification in ("booking_confirmed", "booking_rescheduled"):
        return [name, number, booking.service_names(order), booking.appointment_text(order)]
    if notification == "booking_cancelled":
        return [name, number, order.cancel_reason or EMPTY_PARAM]
    if notification == "confirmed":
        return [name, number, format_inr(order.total_paise), payment_phrase(order)]
    if notification == "shipped":
        return [
            name,
            number,
            order.courier_name or NO_COURIER,
            order.awb_number or EMPTY_PARAM,
            order.tracking_url or EMPTY_PARAM,
        ]
    if notification == "cancelled":
        return [name, number, order.cancel_reason or EMPTY_PARAM]
    if notification == "payment_reminder":
        return [name, number, format_inr(order.total_paise), payment_url or EMPTY_PARAM]
    return [name, number]


def shipped_text(name: str, order: Order) -> str:
    """The in-window shipped update, mentioning only the tracking details the seller gave."""
    courier = f" with {order.courier_name}" if order.courier_name else ""
    if not (order.courier_name or order.awb_number or order.tracking_url):
        return f"Hi {name}, your order {order.number} has shipped and is on its way to you."
    awb = f" AWB: {order.awb_number}." if order.awb_number else ""
    return f"Hi {name}, your order {order.number} has shipped{courier}.{awb}"


def payment_phrase(order: Order) -> str:
    if order.payment_method == Order.PaymentMethod.COD:
        return "Cash on delivery"
    if (
        order.payment_method == Order.PaymentMethod.PAY_AT_SHOP
        or order.payment_status == Order.PaymentStatus.ADVANCE_PAID
    ):
        return buyer.payment_label(order)
    return "Paid online"


def session_content(order: Order, notification: str, *, payment_link=None):
    """The in-window message for a status notification."""
    footer = footer_for(get_store_settings(order.workspace))
    view = [(build_reply_id("ord", "view", order.pk), "View order")]
    name = buyer.buyer_name(order)
    if notification == "payment_reminder":
        noun = "booking" if order.is_booking else "order"
        amount = format_inr(payment_link.amount_paise)
        body = (
            f"Hi {name}, your {noun} {order.number} is waiting for payment of {amount}. "
            "Tap below to pay before the link expires."
        )
        return interactive.cta_url(
            body, f"Pay {amount}"[:20], payment_link.short_url, footer=footer
        )
    if notification.startswith("booking_"):
        return booking_session_content(order, notification, name=name, view=view, footer=footer)
    if notification == "confirmed":
        body = "\n".join(
            [
                f"Thank you, {name}! Your order is confirmed.",
                "",
                buyer.order_summary(order),
                "",
                f"Payment: {payment_phrase(order)}",
                "We'll message you when it ships.",
            ]
        )
        return interactive.reply_buttons(buyer.truncate(body), view, footer=footer)
    if notification == "packed":
        body = f"Hi {name}, your order {order.number} is packed and will be shipped soon."
        return interactive.reply_buttons(body, view, footer=footer)
    if notification == "shipped":
        body = shipped_text(name, order)
        if order.tracking_url:
            return interactive.cta_url(body, "Track order", order.tracking_url, footer=footer)
        return interactive.reply_buttons(body, view, footer=footer)
    if notification == "delivered":
        body = (
            f"Hi {name}, your order {order.number} has been delivered. "
            "Thank you for shopping with us!"
        )
        return interactive.reply_buttons(body, view, footer=footer)
    if notification == "cancelled":
        reason = f" Reason: {order.cancel_reason}." if order.cancel_reason else ""
        body = f"Hi {name}, your order {order.number} has been cancelled.{reason}"
        return sending.TextContent(body + cancelled_payment_text(order))
    raise ValueError(f"Unknown order notification {notification!r}.")


def booking_session_content(order: Order, notification: str, *, name, view, footer):
    when = booking.appointment_text(order)
    services = booking.service_names(order)
    if notification == "booking_confirmed":
        body = "\n".join(
            [
                f"Thank you, {name}! Your booking {order.number} is confirmed.",
                "",
                f"*{services}*",
                f"*When:* {when}",
                f"Payment: {payment_phrase(order)}",
                "",
                "See you then!",
            ]
        )
        return interactive.reply_buttons(buyer.truncate(body), view, footer=footer)
    if notification == "booking_rescheduled":
        body = (
            f"Hi {name}, the time of your booking {order.number} ({services}) has changed. "
            f"New time: {when}."
        )
        return interactive.reply_buttons(buyer.truncate(body), view, footer=footer)
    if notification in REMINDERS:
        lead = "see you tomorrow" if notification == "booking_day_before" else "see you soon"
        body = "\n".join(
            [
                f"Hi {name}, a reminder of your booking {order.number}: {lead}!",
                "",
                f"*{services}*",
                f"*When:* {when}",
                booking_payment_note(order),
                "",
                "Will you be there?",
            ]
        )
        return interactive.reply_buttons(
            buyer.truncate(body), reminder_buttons(order), footer=footer
        )
    if notification == "booking_cancelled":
        reason = f" Reason: {order.cancel_reason}." if order.cancel_reason else ""
        body = f"Hi {name}, your booking {order.number} has been cancelled.{reason}"
        return sending.TextContent(body + cancelled_payment_text(order))
    raise ValueError(f"Unknown order notification {notification!r}.")


def notify_buyer(
    order: Order, notification: str, *, actor: str, user=None, payment_link=None
) -> Message | None:
    """Tell the buyer about a status change. Call inside the transaction that changed it.

    ``payment_reminder`` needs the open ``payment_link`` (its URL and amount)."""
    notification = notification_key(order, notification)
    idempotency_key = buyer.key(order.pk, "notify", notification, order.updated_at.timestamp())
    if sending.window_open(order.contact, order.phone_number):
        content = session_content(order, notification, payment_link=payment_link)
        message = buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)
        if message is None:
            return _failed(order, notification, actor, user, "The message could not be sent.")
        return _sent(order, notification, actor, user, message, "session message")

    store_settings = get_store_settings(order.workspace)
    field = template_field(notification)
    template = getattr(store_settings, field) if field else None
    if template is None:
        return _failed(
            order,
            notification,
            actor,
            user,
            "The buyer's 24-hour window is closed and no template is mapped for this update.",
        )
    if template.status != MessageTemplate.Status.APPROVED:
        return _failed(
            order, notification, actor, user, f"The template {template.name} is not approved."
        )
    button_params = quick_reply_payloads(template, order) if notification in REMINDERS else None
    payment_url = payment_link.short_url if payment_link is not None else ""
    content = sending.TemplateContent(
        template,
        template_params(order, notification, payment_url=payment_url),
        button_params=button_params or None,
    )
    message = buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)
    if message is None:
        return _failed(
            order, notification, actor, user, f"The template {template.name} could not be sent."
        )
    return _sent(order, notification, actor, user, message, f"template {template.name}")


def _sent(order, notification, actor, user, message, how) -> Message:
    OrderEvent.objects.create(
        workspace_id=order.workspace_id,
        order=order,
        type=OrderEvent.Type.NOTIFICATION_SENT,
        actor=actor,
        user=user,
        detail=f"Buyer notified ({notification}) with a {how}.",
        message=message,
        metadata={"notification": notification},
    )
    return message


def _failed(order, notification, actor, user, detail) -> None:
    OrderEvent.objects.create(
        workspace_id=order.workspace_id,
        order=order,
        type=OrderEvent.Type.NOTIFICATION_FAILED,
        actor=actor,
        user=user,
        detail=detail,
        metadata={"notification": notification},
    )
    return None
