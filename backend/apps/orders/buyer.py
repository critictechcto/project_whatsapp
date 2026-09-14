"""Messages to buyers: sending with policy errors logged instead of raised, and the shared text
(order summaries, addresses, status cards).

Every commerce message is sent with source ``automation`` and ``source_ref`` ``order:<id>`` (the
inbox has no commerce source). Pass an idempotency key derived from the triggering inbound
message or state change, so a redelivered event never sends twice.
"""

import logging

from rest_framework.exceptions import ValidationError

from apps.inbox import sending
from apps.inbox.interactive import InvalidInteractiveContent
from apps.inbox.models import Conversation, Message

from .models import Order
from .money import format_inr

logger = logging.getLogger(__name__)

SOURCE = Message.Source.AUTOMATION
SOURCE_REF_PREFIX = "order:"
MAX_SUMMARY_LINES = 12
IDEMPOTENCY_KEY_MAX_LENGTH = 255

STATUS_LABELS = {
    Order.Status.DRAFT: "Draft",
    Order.Status.AWAITING_CONFIRMATION: "Waiting for your confirmation",
    Order.Status.AWAITING_ADDRESS: "Waiting for your address",
    Order.Status.AWAITING_PAYMENT_METHOD: "Choose a payment method",
    Order.Status.PENDING_PAYMENT: "Waiting for payment",
    Order.Status.CONFIRMED: "Confirmed",
    Order.Status.PACKED: "Packed",
    Order.Status.SHIPPED: "Shipped",
    Order.Status.DELIVERED: "Delivered",
    Order.Status.CANCELLED: "Cancelled",
    Order.Status.EXPIRED: "Expired",
    Order.Status.NEEDS_ATTENTION: "Being reviewed by the store",
}
PAYMENT_LABELS = {
    Order.PaymentStatus.UNPAID: "Not paid",
    Order.PaymentStatus.PAID: "Paid online",
    Order.PaymentStatus.COD_PENDING: "Cash on delivery",
    Order.PaymentStatus.COD_COLLECTED: "Cash on delivery (paid)",
    Order.PaymentStatus.REFUNDED_MANUAL: "Refunded",
}


def source_ref(order: Order) -> str:
    return f"{SOURCE_REF_PREFIX}{order.pk}"


def key(*parts: object) -> str:
    return ":".join(["orders", *(str(part) for part in parts)])[:IDEMPOTENCY_KEY_MAX_LENGTH]


def send_to_buyer(order: Order, content, *, idempotency_key: str | None = None) -> Message | None:
    """Send ``content`` to the order's buyer on the order's number; None when not allowed."""
    conversation = order.conversation
    if conversation is not None and conversation.phone_number_id != order.phone_number_id:
        conversation = None
    return _send(
        workspace=order.workspace,
        contact=order.contact,
        conversation=conversation,
        phone_number=order.phone_number,
        content=content,
        ref=source_ref(order),
        idempotency_key=idempotency_key,
    )


def send_in_conversation(
    conversation: Conversation, content, *, ref: str = "", idempotency_key: str | None = None
) -> Message | None:
    return _send(
        workspace=conversation.workspace,
        contact=conversation.contact,
        conversation=conversation,
        phone_number=None,
        content=content,
        ref=ref,
        idempotency_key=idempotency_key,
    )


def _send(*, workspace, contact, conversation, phone_number, content, ref, idempotency_key):
    try:
        return sending.send_message(
            workspace=workspace,
            contact=contact,
            conversation=conversation,
            phone_number=phone_number,
            content=content,
            source=SOURCE,
            source_ref=ref,
            idempotency_key=idempotency_key,
        )
    except (sending.SendPolicyError, InvalidInteractiveContent, ValidationError) as exc:
        logger.info("Commerce message to contact %s not sent (%s): %s", contact.pk, ref, exc)
        return None


# --- Text -----------------------------------------------------------------------------------


def buyer_name(order: Order) -> str:
    return (order.contact.name or "").strip() or "Customer"


def item_lines(order: Order) -> list[str]:
    items = list(order.items.all())
    lines = [
        f"{item.quantity} x {item.name} — {format_inr(item.line_total_paise)}"
        for item in items[:MAX_SUMMARY_LINES]
    ]
    if len(items) > MAX_SUMMARY_LINES:
        lines.append(f"…and {len(items) - MAX_SUMMARY_LINES} more")
    return lines


def totals_lines(order: Order) -> list[str]:
    lines = [f"Subtotal: {format_inr(order.subtotal_paise)}"]
    lines.append(
        f"Shipping: {format_inr(order.shipping_paise)}"
        if order.shipping_paise
        else "Shipping: Free"
    )
    if order.cod_fee_paise:
        lines.append(f"Cash on delivery fee: {format_inr(order.cod_fee_paise)}")
    lines.append(f"*Total: {format_inr(order.total_paise)}*")
    return lines


def order_summary(order: Order) -> str:
    return "\n".join([f"*Order {order.number}*", *item_lines(order), "", *totals_lines(order)])


def format_address(address: dict | None) -> str:
    if not address:
        return ""
    parts = [
        address.get("name", ""),
        address.get("line1", ""),
        address.get("line2", ""),
        address.get("landmark", ""),
        ", ".join(filter(None, [address.get("city", ""), address.get("state", "")])),
        address.get("pincode", ""),
    ]
    return "\n".join(part for part in parts if part)


def payment_label(order: Order) -> str:
    return PAYMENT_LABELS.get(order.payment_status, order.payment_status)


def status_card(order: Order) -> str:
    lines = [
        f"*Order {order.number}*",
        f"Status: {STATUS_LABELS.get(order.status, order.status)}",
        f"Payment: {payment_label(order)}",
        "",
        *item_lines(order),
        "",
        f"*Total: {format_inr(order.total_paise)}*",
    ]
    if order.courier_name or order.awb_number:
        lines.append("")
        lines.append(f"Courier: {order.courier_name or '—'}  AWB: {order.awb_number or '—'}")
    return truncate("\n".join(lines))


def truncate(text: str, limit: int = 1024) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
