"""Buyer notifications on status changes (docs/contracts/wave-3-commerce.md, "Starter templates").

Inside the 24-hour customer service window the buyer gets a session message (text or
interactive). Outside it, the template mapped in ``StoreSettings.notification_templates`` is sent
with body parameters in the contract order. Every attempt writes an ``OrderEvent``:
``notification_sent`` (with the message) or ``notification_failed``.
"""

from apps.inbox import interactive, sending
from apps.inbox.models import Message
from apps.message_templates.models import MessageTemplate
from common.commerce import build_reply_id

from . import buyer
from .models import Order, OrderEvent, StoreSettings
from .money import format_inr
from .store import footer_for, get_store_settings

EMPTY_PARAM = "—"
NOTIFIED_STATUSES = ("confirmed", "packed", "shipped", "delivered", "cancelled")


def template_params(order: Order, notification: str, *, payment_url: str = "") -> list[str]:
    """Body parameters of the ``upc_order_*`` starter template for ``notification``."""
    name, number = buyer.buyer_name(order), order.number
    if notification == "confirmed":
        return [name, number, format_inr(order.total_paise), payment_phrase(order)]
    if notification == "shipped":
        return [
            name,
            number,
            order.courier_name or EMPTY_PARAM,
            order.awb_number or EMPTY_PARAM,
            order.tracking_url or EMPTY_PARAM,
        ]
    if notification == "cancelled":
        return [name, number, order.cancel_reason or EMPTY_PARAM]
    if notification == "payment_reminder":
        return [name, number, format_inr(order.total_paise), payment_url or EMPTY_PARAM]
    return [name, number]


def payment_phrase(order: Order) -> str:
    if order.payment_method == Order.PaymentMethod.COD:
        return "Cash on delivery"
    return "Paid online"


def session_content(order: Order, notification: str):
    """The in-window message for a status notification."""
    footer = footer_for(get_store_settings(order.workspace))
    view = [(build_reply_id("ord", "view", order.pk), "View order")]
    name = buyer.buyer_name(order)
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
        body = (
            f"Hi {name}, your order {order.number} has shipped with "
            f"{order.courier_name or 'our courier'}. AWB: {order.awb_number or EMPTY_PARAM}."
        )
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
        if order.payment_status == Order.PaymentStatus.PAID:
            body += " The store will refund your payment."
        return sending.TextContent(body)
    raise ValueError(f"Unknown order notification {notification!r}.")


def notify_buyer(order: Order, notification: str, *, actor: str, user=None) -> Message | None:
    """Tell the buyer about a status change. Call inside the transaction that changed it."""
    idempotency_key = buyer.key(order.pk, "notify", notification, order.updated_at.timestamp())
    if sending.window_open(order.contact, order.phone_number):
        content = session_content(order, notification)
        message = buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)
        if message is None:
            return _failed(order, notification, actor, user, "The message could not be sent.")
        return _sent(order, notification, actor, user, message, "session message")

    store_settings = get_store_settings(order.workspace)
    field = StoreSettings.NOTIFICATION_TEMPLATE_FIELDS.get(notification)
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
    content = sending.TemplateContent(template, template_params(order, notification))
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
