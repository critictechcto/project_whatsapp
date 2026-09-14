"""Builders shared by the orders tests: carts, buyer replies, events and outbound inspection."""

import json
import re
from datetime import timedelta

from django.utils import timezone

from apps.catalog.services import PricedCart, PricedLine
from apps.inbox.factories import MessageFactory
from apps.inbox.models import Message
from apps.orders import services
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.orders.models import Order
from common.commerce import build_reply_id, parse_reply_id
from common.events import (
    MessageDeliveryUpdated,
    MessageRecorded,
    PaymentLinkCancelled,
    PaymentLinkExpired,
    PaymentLinkPaid,
)

REPLY_ID_RE = re.compile(r'"(upc:[^"]+)"')

VALID_FORM = {
    "name": "Asha Verma",
    "phone_number": "+919876543210",
    "in_pin_code": "411001",
    "house_number": "12",
    "building_name": "Lotus Apartments",
    "address": "MG Road",
    "landmark_area": "Camp",
    "city": "Pune",
    "state": "Maharashtra",
}


def priced_cart(*lines, dropped=()) -> PricedCart:
    priced = tuple(
        PricedLine(
            product=product,
            quantity=quantity,
            unit_price_paise=product.price_paise,
            line_total_paise=product.price_paise * quantity,
        )
        for product, quantity in lines
    )
    return PricedCart(
        lines=priced,
        dropped=tuple(dropped),
        subtotal_paise=sum(line.line_total_paise for line in priced),
    )


def start(conversation, *lines, dropped=(), source="bot", **kwargs) -> Order:
    return services.start_checkout(
        workspace=conversation.workspace,
        conversation=conversation,
        cart=priced_cart(*lines, dropped=dropped),
        source=source,
        **kwargs,
    )


def refresh(order) -> Order:
    return Order.objects.get(pk=order.pk)


def event_types(order) -> list[str]:
    return list(order.events.order_by("created_at", "pk").values_list("type", flat=True))


def outbound(contact) -> list[Message]:
    return list(
        Message.objects.filter(
            conversation__contact=contact, direction=Message.Direction.OUTBOUND
        ).order_by("created_at", "pk")
    )


def last_outbound(contact) -> Message:
    messages = outbound(contact)
    assert messages, "no outbound message was sent"
    return messages[-1]


def reply_ids(message) -> list[str]:
    return REPLY_ID_RE.findall(json.dumps(message.payload))


def interactive_type(message) -> str | None:
    return (message.payload.get("interactive") or {}).get("type")


def content_text(message) -> str:
    return f"{message.text}\n{json.dumps(message.payload, ensure_ascii=False)}"


def press(conversation, reply_id: str, *, message=None) -> Message:
    """The buyer taps a button or list row with ``reply_id``; the shop forwards it."""
    if message is None:
        message = MessageFactory(
            inbound=True,
            conversation=conversation,
            type=Message.Type.INTERACTIVE,
            text="",
            payload={
                "type": "interactive",
                "interactive": {"type": "button_reply", "button_reply": {"id": reply_id}},
            },
        )
    assert services.handle_checkout_reply(message, parse_reply_id(reply_id)) is True
    return message


def submit_address(conversation, values=None) -> Message:
    """The buyer submits WhatsApp's address form."""
    response_json = json.dumps({"values": VALID_FORM if values is None else values})
    message = MessageFactory(
        inbound=True,
        conversation=conversation,
        type=Message.Type.INTERACTIVE,
        text="",
        payload={
            "type": "interactive",
            "interactive": {
                "type": "nfm_reply",
                "nfm_reply": {
                    "name": "address_message",
                    "body": "Sent",
                    "response_json": response_json,
                },
            },
        },
    )
    reply = parse_reply_id(build_reply_id("nfm", "address_message"))
    assert services.handle_checkout_reply(message, reply) is True
    return message


def typed(conversation, text: str) -> Message:
    return MessageFactory(
        inbound=True, conversation=conversation, type=Message.Type.TEXT, text=text
    )


def pending_order(conversation, product, *, quantity=1, **fields) -> Order:
    """An online checkout waiting for payment with its stock reserved (stock is not moved)."""
    values = {
        "workspace": conversation.workspace,
        "contact": conversation.contact,
        "phone_number": conversation.phone_number,
        "conversation": conversation,
        "status": Order.Status.PENDING_PAYMENT,
        "payment_status": Order.PaymentStatus.UNPAID,
        "payment_method": Order.PaymentMethod.ONLINE,
        "stock_reserved": True,
        "checkout_attempt": 1,
        "item_count": quantity,
        "subtotal_paise": product.price_paise * quantity,
        "total_paise": product.price_paise * quantity,
        "expires_at": timezone.now() + timedelta(minutes=30),
    }
    values.update(fields)
    order = OrderFactory(**values)
    OrderItemFactory(
        order=order,
        product=product,
        sku=product.sku,
        name=product.name,
        unit_price_paise=product.price_paise,
        quantity=quantity,
    )
    return order


def recorded_event(message) -> MessageRecorded:
    conversation = message.conversation
    return MessageRecorded(
        workspace_id=message.workspace_id,
        message_id=message.pk,
        conversation_id=conversation.pk,
        contact_id=conversation.contact_id,
        phone_number_id=conversation.phone_number_id,
        direction=message.direction,
        source=message.source,
        source_ref=message.source_ref,
        type=message.type,
        text=message.text,
        reply_id=None,
        wamid=message.wamid,
        is_first_inbound=False,
        contact_created=False,
        created_at=message.created_at,
    )


def delivery_failed_event(message, error_code="1026") -> MessageDeliveryUpdated:
    return MessageDeliveryUpdated(
        workspace_id=message.workspace_id,
        message_id=message.pk,
        conversation_id=message.conversation_id,
        source=message.source,
        source_ref=message.source_ref,
        status=Message.Status.FAILED,
        error_code=error_code,
        occurred_at=timezone.now(),
    )


def paid_event(link) -> PaymentLinkPaid:
    return PaymentLinkPaid(
        workspace_id=link.workspace_id,
        order_id=link.order_id,
        payment_link_id=link.pk,
        provider="razorpay",
        provider_link_id=link.provider_link_id,
        provider_payment_id=f"pay_{link.pk.hex[:14]}",
        amount_paise=link.amount_paise,
        currency="INR",
        paid_at=timezone.now(),
    )


def expired_event(link) -> PaymentLinkExpired:
    return PaymentLinkExpired(
        workspace_id=link.workspace_id,
        order_id=link.order_id,
        payment_link_id=link.pk,
        provider="razorpay",
        provider_link_id=link.provider_link_id,
        occurred_at=timezone.now(),
    )


def cancelled_event(link) -> PaymentLinkCancelled:
    return PaymentLinkCancelled(
        workspace_id=link.workspace_id,
        order_id=link.order_id,
        payment_link_id=link.pk,
        provider="razorpay",
        provider_link_id=link.provider_link_id,
        occurred_at=timezone.now(),
    )
