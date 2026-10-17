"""Buyer checkout on WhatsApp (docs/contracts/wave-3-commerce.md, "Orders services").

Flow: re-priced cart → confirmation when the price changed → address (a returning buyer first
gets their saved address with *Deliver here* / *Change address*; otherwise ``address_message``,
or typed text for non-Indian numbers and clients that fail it with error 1026) → payment choice
(online link on the seller's gateway, or cash on delivery) → confirmed.

Every buyer reply is re-validated against the order row under ``select_for_update``. Replies to
one inbound message are sent with idempotency keys ``orders:<message_id>:<step>``, and a message
that already has such a reply is not handled again, so redelivered events never double-send.

Bookings (services, docs/contracts/services-and-offers.md) skip the address: the buyer picks a
day (``chk:day``) and a window (``chk:win``), then *Pay online* or *Pay at the shop*; the
finished checkout lands in ``requested`` for the seller to confirm a time. A claimed offer code
is applied when the checkout starts (or later, :func:`apply_offer_to_active_checkout`).
"""

import json
import logging
import re
import uuid
from datetime import timedelta
from functools import partial

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services import OutOfStock, PricedCart, public_image_url
from apps.contacts.models import Contact
from apps.inbox import interactive, sending
from apps.inbox.models import Conversation, Message
from apps.offers import services as offers
from apps.payments import services as payment_services
from apps.payments.exceptions import (
    PaymentAccountInvalid,
    PaymentAccountMissing,
    PaymentProviderError,
)
from common.commerce import ReplyId, build_reply_id
from common.events import MessageDeliveryUpdated, MessageRecorded
from common.phone import InvalidPhoneNumber, normalize_e164

from . import booking, buyer, lifecycle, notifications, transitions
from .exceptions import CheckoutRejected
from .models import Order, OrderEvent, OrderItem, ShopperAddress
from .money import format_inr
from .store import (
    checkout_ttl_minutes,
    footer_for,
    get_store_settings,
    next_order_number,
    payment_link_expiry_minutes,
    store_display_name,
)

logger = logging.getLogger(__name__)

Status = Order.Status
BUYER = OrderEvent.Actor.BUYER
SYSTEM = OrderEvent.Actor.SYSTEM

INDIA_PREFIX = "+91"
ADDRESS_UNSUPPORTED_ERROR = "1026"
PINCODE_RE = re.compile(r"^[0-9]{6}$")
PINCODE_IN_TEXT_RE = re.compile(r"(?<!\d)(\d{3})\s?(\d{3})(?!\d)")
STALE_TEXT = "This option is no longer available."
MAX_RECENT_ORDERS = 10

DROP_REASONS = {
    "unknown": "is no longer sold",
    "inactive": "is not available right now",
    "out_of_stock": "is out of stock",
}

INDIAN_STATES = (
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
)
_STATES_BY_KEY = {state.lower(): state for state in INDIAN_STATES}


# --- Helpers ------------------------------------------------------------------------------------


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _deadline():
    return timezone.now() + timedelta(minutes=checkout_ttl_minutes())


def _conversation_of(message: Message) -> Conversation:
    return Conversation.objects.select_related("workspace", "contact", "phone_number__waba").get(
        pk=message.conversation_id
    )


def _lock_conversation(conversation_id) -> Conversation:
    return (
        Conversation.objects.select_for_update(of=("self",))
        .select_related("workspace", "contact", "phone_number__waba")
        .get(pk=conversation_id)
    )


def _already_handled(message: Message) -> bool:
    """A reply keyed on this inbound message, or an order event it caused, exists: a redelivered
    event must do nothing."""
    return (
        Message.objects.filter(
            workspace_id=message.workspace_id,
            idempotency_key__startswith=buyer.key(message.pk, ""),
        ).exists()
        or OrderEvent.objects.filter(workspace_id=message.workspace_id, message=message).exists()
    )


def _lock_checkout(conversation: Conversation, *statuses: str) -> Order | None:
    return (
        Order.objects.select_for_update(of=("self",))
        .select_related("workspace", "contact", "phone_number__waba", "conversation")
        .filter(
            workspace_id=conversation.workspace_id,
            contact_id=conversation.contact_id,
            phone_number_id=conversation.phone_number_id,
            status__in=statuses or transitions.CHECKOUT_STATUSES,
        )
        .first()
    )


def _menu_button() -> tuple[str, str]:
    return (build_reply_id("shop", "menu"), "Menu")


def _cart_button() -> tuple[str, str]:
    return (build_reply_id("shop", "cart"), "View cart")


def _send_stale(conversation: Conversation, message: Message) -> None:
    content = interactive.reply_buttons(STALE_TEXT, [_menu_button()])
    buyer.send_in_conversation(
        conversation, content, idempotency_key=buyer.key(message.pk, "stale")
    )


def shipping_for(store_settings, subtotal_paise: int) -> int:
    threshold = store_settings.free_shipping_above_paise
    if threshold is not None and subtotal_paise >= threshold:
        return 0
    return store_settings.shipping_fee_paise


def order_total(order: Order) -> int:
    """``subtotal - discount + shipping + cod_fee`` (bookings have no shipping or COD fee)."""
    return (
        max(order.subtotal_paise - order.discount_paise, 0)
        + order.shipping_paise
        + order.cod_fee_paise
    )


def cod_allowed(store_settings, order: Order) -> bool:
    if order.is_booking or not store_settings.cod_enabled:
        return False
    limit = store_settings.cod_max_order_paise
    due = max(order.subtotal_paise - order.discount_paise, 0) + order.shipping_paise
    return limit is None or due <= limit


def pay_at_shop_allowed(store_settings, order: Order) -> bool:
    return order.is_booking and store_settings.pay_at_shop_enabled


def online_allowed(order: Order) -> bool:
    return payment_services.online_payments_ready(order.workspace)


def cart_kind(lines) -> str | None:
    """``booking`` for services, ``delivery`` for products, None for a mix."""
    kinds = {
        Order.Kind.BOOKING if line.product.kind == Product.Kind.SERVICE else Order.Kind.DELIVERY
        for line in lines
    }
    return kinds.pop() if len(kinds) == 1 else None


def noun(order: Order) -> str:
    return "booking" if order.is_booking else "order"


def _apply_offer(order: Order) -> bool:
    """Apply the contact's claimed offer to ``order`` (``offers.apply_to_checkout``) and save the
    totals; False when no offer applies or nothing changed."""
    applied = offers.apply_to_checkout(order)
    if applied is None:
        return False
    discount = max(0, min(int(applied.discount_paise), order.subtotal_paise))
    code = (applied.code or "")[:20]
    if (
        order.offer_claim_id == applied.claim_id
        and order.discount_paise == discount
        and order.offer_code == code
    ):
        return False
    order.discount_paise, order.offer_code, order.offer_claim_id = (
        discount,
        code,
        applied.claim_id,
    )
    order.total_paise = order_total(order)
    order.save(
        update_fields=[
            "discount_paise",
            "offer_code",
            "offer_claim_id",
            "total_paise",
            "updated_at",
        ]
    )
    lifecycle.record_event(
        order,
        OrderEvent.Type.OFFER_APPLIED,
        actor=SYSTEM,
        detail=f"Offer {code} applied: {buyer.MINUS}{format_inr(discount)}.",
        metadata={
            "offer_claim_id": str(applied.claim_id),
            "code": code,
            "discount_paise": discount,
        },
    )
    return True


def is_offer_code(workspace_id, text) -> bool:
    return bool(text) and offers.match_code(workspace_id, text) is not None


def dropped_text(cart: PricedCart) -> str:
    lines = []
    for line in cart.dropped:
        label = line.name or line.sku or "An item"
        if line.reason == "quantity_capped":
            lines.append(f"• {label}: only {line.available} can be ordered")
        else:
            lines.append(f"• {label} {DROP_REASONS.get(line.reason, 'is not available')}")
    return "Some items in your cart changed:\n" + "\n".join(lines) if lines else ""


# --- Start --------------------------------------------------------------------------------------


def start_checkout(
    *,
    workspace,
    conversation: Conversation,
    cart: PricedCart,
    source: str,
    source_wamid: str | None = None,
    quoted_total_paise: int | None = None,
) -> Order:
    if source not in Order.Source.values:
        raise ValueError(f"Invalid order source {source!r}.")
    if conversation.workspace_id != workspace.pk:
        raise ValueError("The conversation belongs to a different workspace.")
    source_wamid = source_wamid or ""
    if source_wamid and (existing := _by_source_wamid(workspace, source_wamid)):
        return existing

    store_settings = get_store_settings(workspace)
    conversation = _conversation_of_pk(conversation.pk)
    lines = cart.lines
    subtotal = sum(line.line_total_paise for line in lines)
    notice = dropped_text(cart)
    reject_key = buyer.key("wamid", source_wamid, "rejected") if source_wamid else None
    if not lines:
        body = "\n\n".join(
            filter(None, [notice, "None of the items in your cart can be ordered right now."])
        )
        _send_rejection(conversation, body, source, reject_key)
        raise CheckoutRejected("empty_cart", body)
    kind = cart_kind(lines)
    if kind is None:
        body = (
            "Services and products can't be checked out together. Check out one of them first, "
            "or clear your cart and start again."
        )
        _send_rejection(conversation, body, source, reject_key)
        raise CheckoutRejected("mixed_cart", body)
    is_booking = kind == Order.Kind.BOOKING
    if is_booking:
        name = store_display_name(store_settings)
        if not (
            payment_services.online_payments_ready(workspace) or store_settings.pay_at_shop_enabled
        ):
            body = f"Sorry, {name} isn't taking bookings on WhatsApp right now."
            _send_rejection(conversation, body, source, reject_key)
            raise CheckoutRejected("payment_unavailable", body)
        if not booking.bookable_days(store_settings, workspace):
            body = f"Sorry, {name} has no times open for booking right now. Please try again later."
            _send_rejection(conversation, body, source, reject_key)
            raise CheckoutRejected("no_booking_times", body)
    elif subtotal < store_settings.min_order_paise:
        body = "\n\n".join(
            filter(
                None,
                [
                    notice,
                    f"The minimum order is {format_inr(store_settings.min_order_paise)}. Your "
                    f"cart comes to {format_inr(subtotal)}, so add a little more to check out.",
                ],
            )
        )
        _send_rejection(conversation, body, source, reject_key)
        raise CheckoutRejected("below_minimum", body)

    with transaction.atomic():
        conversation = _lock_conversation(conversation.pk)
        if source_wamid and (existing := _by_source_wamid(workspace, source_wamid)):
            return existing
        _supersede_active_checkout(conversation)

        shipping = 0 if is_booking else shipping_for(store_settings, subtotal)
        price_changed = quoted_total_paise is not None and quoted_total_paise != subtotal
        if price_changed:
            status = Status.AWAITING_CONFIRMATION
        else:
            status = Status.AWAITING_TIME if is_booking else Status.AWAITING_ADDRESS
        order = Order.objects.create(
            workspace=workspace,
            kind=kind,
            contact=conversation.contact,
            conversation=conversation,
            phone_number=conversation.phone_number,
            number=next_order_number(workspace),
            status=status,
            source=source,
            source_wamid=source_wamid,
            item_count=sum(line.quantity for line in lines),
            subtotal_paise=subtotal,
            shipping_paise=shipping,
            total_paise=subtotal + shipping,
            quoted_total_paise=quoted_total_paise,
            expires_at=_deadline(),
        )
        if source_wamid:
            _link_source_message(order)
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    workspace=workspace,
                    order=order,
                    product=line.product,
                    position=position,
                    sku=line.product.sku,
                    name=line.product.name[:200],
                    image_url=(public_image_url(line.product) or "")[:500],
                    unit_price_paise=line.unit_price_paise,
                    quantity=line.quantity,
                    line_total_paise=line.line_total_paise,
                )
                for position, line in enumerate(lines)
            ]
        )
        lifecycle.record_event(
            order,
            OrderEvent.Type.CREATED,
            actor=BUYER,
            to_status=status,
            detail=f"Checkout started ({order.get_source_display().lower()}).",
        )
        if price_changed:
            lifecycle.record_event(
                order,
                OrderEvent.Type.PRICE_CHANGED,
                actor=SYSTEM,
                detail=(
                    f"The cart showed {format_inr(quoted_total_paise)}; current prices come to "
                    f"{format_inr(subtotal)}."
                ),
                metadata={"quoted_total_paise": quoted_total_paise, "subtotal_paise": subtotal},
            )
        _apply_offer(order)
        lifecycle.emit_status_changed(order, "", actor=BUYER)
        lifecycle.broadcast_created(order)

        if notice:
            buyer.send_to_buyer(
                order, sending.TextContent(notice), idempotency_key=buyer.key(order.pk, "dropped")
            )
        if price_changed:
            _ask_confirmation(order, store_settings)
        elif is_booking:
            ask_day(order, store_settings, idempotency_key=buyer.key(order.pk, "day"))
        else:
            ask_address(order, store_settings, idempotency_key=buyer.key(order.pk, "address"))
    return order


def _conversation_of_pk(pk) -> Conversation:
    return Conversation.objects.select_related("workspace", "contact", "phone_number__waba").get(
        pk=pk
    )


def _link_source_message(order: Order) -> None:
    """Link the inbound cart or checkout tap that started ``order`` to it (``Message.order_id``)."""
    Message.objects.filter(
        workspace_id=order.workspace_id,
        wamid=order.source_wamid,
        direction=Message.Direction.INBOUND,
        source_ref="",
    ).update(source_ref=buyer.source_ref(order))


def _by_source_wamid(workspace, source_wamid: str) -> Order | None:
    return Order.objects.filter(workspace=workspace, source_wamid=source_wamid).first()


def _send_rejection(conversation, body: str, source: str, idempotency_key) -> None:
    if source == Order.Source.BOT:
        content = interactive.reply_buttons(buyer.truncate(body), [_cart_button()])
    else:
        content = sending.TextContent(body)
    buyer.send_in_conversation(conversation, content, idempotency_key=idempotency_key)


def _supersede_active_checkout(conversation: Conversation) -> None:
    active = _lock_checkout(conversation)
    if active is None:
        return
    lifecycle.cancel_order(
        active, actor=BUYER, reason="Replaced by a new checkout.", notify_buyer=False
    )
    buyer.send_to_buyer(
        active,
        sending.TextContent(f"Your earlier checkout {active.number} was replaced by this new one."),
        idempotency_key=buyer.key(active.pk, "superseded"),
    )


def _ask_confirmation(order: Order, store_settings) -> None:
    body = "\n".join(
        [
            "Some prices changed since these items were added. Here is your updated order:",
            "",
            buyer.order_summary(order),
            "",
            "Shall we continue?",
        ]
    )
    content = interactive.reply_buttons(
        buyer.truncate(body),
        [
            (build_reply_id("chk", "confirm", order.pk), "Confirm"),
            (build_reply_id("chk", "edit", order.pk), "Edit cart"),
        ],
        footer=footer_for(store_settings),
    )
    buyer.send_to_buyer(order, content, idempotency_key=buyer.key(order.pk, "confirm"))


# --- Booking day and window ---------------------------------------------------------------------


def _cancel_button(order: Order) -> tuple[str, str]:
    return (build_reply_id("chk", "cancel", order.pk), f"Cancel {noun(order)}")


def ask_day(
    order: Order, store_settings, *, idempotency_key: str, note: str = ""
) -> Message | None:
    """The list of open days (``chk:day``)."""
    days = booking.bookable_days(store_settings, order.workspace)
    footer = footer_for(store_settings)
    if not days:
        body = "\n\n".join(
            filter(None, [note, "Sorry, there are no times open for booking right now."])
        )
        content = interactive.reply_buttons(body, [_cancel_button(order)], footer=footer)
        return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)
    today = booking.local_now(order.workspace).date()
    rows = []
    for day in days:
        title = booking.day_title(day, today)
        rows.append(
            interactive.ListRow(
                id=build_reply_id("chk", "day", order.pk, booking.day_arg(day)),
                title=title[:24],
                description="" if title == booking.format_day(day) else booking.format_day(day),
            )
        )
    lines = [note, ""] if note else []
    lines += [buyer.order_summary(order), "", "Which day would you like to come in?"]
    content = interactive.list_message(
        buyer.truncate("\n".join(lines)),
        "Choose a day",
        [interactive.ListSection("Open days", rows)],
        footer=footer,
    )
    return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)


def ask_window(order: Order, store_settings, day, *, idempotency_key: str) -> Message | None:
    """The windows still open on ``day`` (``chk:win``): reply buttons for up to three, else a
    list."""
    open_windows = booking.open_windows(store_settings, order.workspace, day)
    footer = footer_for(store_settings)
    body = f"{booking.format_day(day)}: which time suits you?"
    if len(open_windows) <= interactive.MAX_BUTTONS:
        lines = [body, ""] + [f"• {booking.window_text(window)}" for _, window in open_windows]
        content = interactive.reply_buttons(
            "\n".join(lines),
            [
                (build_reply_id("chk", "win", order.pk, index), window["label"][:20])
                for index, window in open_windows
            ],
            footer=footer,
        )
    else:
        rows = [
            interactive.ListRow(
                id=build_reply_id("chk", "win", order.pk, index),
                title=window["label"][:24],
                description=f"{window['start']}-{window['end']}",
            )
            for index, window in open_windows
        ]
        content = interactive.list_message(
            body, "Choose a time", [interactive.ListSection("Times", rows)], footer=footer
        )
    return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)


def _send_request_received(order: Order, *, idempotency_key: str) -> Message | None:
    """The booking reached ``requested``: tell the buyer the store will confirm the time."""
    body = "\n".join(
        [
            f"Thank you, {buyer.buyer_name(order)}! We've received your booking request.",
            "",
            buyer.order_summary(order),
            "",
            f"Payment: {buyer.payment_label(order)}",
            "The store will confirm your time shortly.",
        ]
    )
    content = interactive.reply_buttons(
        buyer.truncate(body),
        [(build_reply_id("ord", "view", order.pk), "View booking")],
        footer=footer_for(get_store_settings(order.workspace)),
    )
    return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)


# --- Address ------------------------------------------------------------------------------------


def address_by_text(workspace_id, contact: Contact) -> bool:
    """Ask for a typed address: non-Indian numbers, and buyers whose WhatsApp can't show the
    address form (a previous ``address_message`` failed with error 1026)."""
    if not (contact.phone_e164 or "").startswith(INDIA_PREFIX):
        return True
    return Message.objects.filter(
        workspace_id=workspace_id,
        conversation__contact_id=contact.pk,
        direction=Message.Direction.OUTBOUND,
        error_code=ADDRESS_UNSUPPORTED_ERROR,
    ).exists()


def awaiting_address_text(workspace_id, contact_id, phone_number_id) -> bool:
    """True while a checkout for this contact and number waits for a typed address."""
    if not Order.objects.filter(
        workspace_id=workspace_id,
        contact_id=contact_id,
        phone_number_id=phone_number_id,
        status=Status.AWAITING_ADDRESS,
    ).exists():
        return False
    contact = Contact.objects.filter(pk=contact_id).only("pk", "phone_e164").first()
    return contact is not None and address_by_text(workspace_id, contact)


def claim_awaited_text(event: MessageRecorded) -> bool:
    """Commerce claimer: typed text while a checkout awaits a typed address."""
    if event.direction != Message.Direction.INBOUND or event.type != Message.Type.TEXT:
        return False
    if is_offer_code(event.workspace_id, event.text):
        return False
    return awaiting_address_text(event.workspace_id, event.contact_id, event.phone_number_id)


def _form_values(address: dict | None, contact: Contact) -> dict[str, str]:
    if not address:
        values = {"name": contact.name or "", "phone_number": contact.phone_e164 or ""}
    else:
        values = {
            "name": address.get("name", ""),
            "phone_number": address.get("phone_e164", ""),
            "in_pin_code": address.get("pincode", ""),
            "address": address.get("line1", ""),
            "building_name": address.get("line2", ""),
            "landmark_area": address.get("landmark", ""),
            "city": address.get("city", ""),
            "state": address.get("state", ""),
        }
    return {k: str(v) for k, v in values.items() if v}


def saved_address(order: Order, store_settings) -> dict | None:
    """The buyer's last used address when it is complete and still deliverable, else None."""
    saved = ShopperAddress.objects.filter(
        workspace_id=order.workspace_id, contact_id=order.contact_id
    ).first()
    address = saved.address if saved is not None else None
    if not isinstance(address, dict):
        return None
    if not all(str(address.get(field) or "").strip() for field in ("name", "line1", "city")):
        return None
    if _serviceable_error(store_settings, str(address.get("pincode") or "")):
        return None
    return address


def ask_address(order: Order, store_settings, *, idempotency_key: str) -> Message | None:
    """First address question of a checkout: one tap for a returning buyer's saved address."""
    address = saved_address(order, store_settings)
    if address is None:
        return request_address(order, idempotency_key=idempotency_key)
    body = f"Deliver order {order.number} to:\n\n{buyer.format_address(address)}"
    content = interactive.reply_buttons(
        buyer.truncate(body),
        [
            (build_reply_id("chk", "addr_use", order.pk), "Deliver here"),
            (build_reply_id("chk", "addr_new", order.pk), "Change address"),
        ],
        footer=footer_for(store_settings),
    )
    return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)


def request_address(
    order: Order,
    *,
    idempotency_key: str,
    values: dict[str, str] | None = None,
    validation_errors: dict[str, str] | None = None,
) -> Message | None:
    """Ask for the delivery address with the native form, or as typed text."""
    if address_by_text(order.workspace_id, order.contact):
        body = (
            f"Where should we deliver order {order.number}? Please type the full address in one "
            "message:\n\nName\nHouse / street\nArea, landmark\nCity, State\n6-digit pincode"
        )
        return buyer.send_to_buyer(
            order, sending.TextContent(body), idempotency_key=idempotency_key
        )
    if values is None:
        saved = ShopperAddress.objects.filter(
            workspace_id=order.workspace_id, contact_id=order.contact_id
        ).first()
        values = _form_values(saved.address if saved else None, order.contact)
    body = f"Where should we deliver order {order.number}? Tap below to share your address."
    if validation_errors:
        body = f"Please check the highlighted fields for order {order.number}."
    content = interactive.address_message(
        body, values=values or None, validation_errors=validation_errors or None
    )
    return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)


def _nfm_values(payload) -> dict[str, str]:
    body = payload.get("interactive") if isinstance(payload, dict) else None
    reply = body.get("nfm_reply") if isinstance(body, dict) else None
    raw = reply.get("response_json") if isinstance(reply, dict) else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if not isinstance(raw, dict):
        return {}
    values = raw.get("values") if isinstance(raw.get("values"), dict) else raw
    return {str(k): str(v).strip() for k, v in values.items() if isinstance(v, str | int)}


def _normalize_phone(value: str, fallback: str) -> str:
    try:
        return normalize_e164(value) if value else fallback
    except InvalidPhoneNumber:
        return fallback


def _serviceable_error(store_settings, pincode: str) -> str | None:
    if not PINCODE_RE.fullmatch(pincode):
        return "Enter a valid 6-digit pincode."
    allowlist = store_settings.serviceable_pincodes or []
    if allowlist and pincode not in allowlist:
        return "Sorry, we don't deliver to this pincode yet."
    return None


def address_from_form(
    values: dict[str, str], order: Order, store_settings
) -> tuple[dict, dict[str, str]]:
    """``(address, errors)`` from ``address_message`` values; errors use the form's field names."""
    contact = order.contact
    floor = values.get("floor_number", "")
    extra = ", ".join(
        part
        for part in (
            values.get("house_number", ""),
            f"Floor {floor}" if floor else "",
            values.get("tower_number", ""),
            values.get("building_name", ""),
        )
        if part
    )
    line1, line2 = values.get("address", ""), extra
    if not line1:
        line1, line2 = extra, ""
    address = {
        "name": (values.get("name") or contact.name or "")[:100],
        "phone_e164": _normalize_phone(values.get("phone_number", ""), contact.phone_e164)[:16],
        "line1": line1[:200],
        "line2": line2[:200],
        "landmark": values.get("landmark_area", "")[:200],
        "city": values.get("city", "")[:100],
        "state": values.get("state", "")[:100],
        "pincode": re.sub(r"\s", "", values.get("in_pin_code", "")),
        "country": "IN",
    }
    errors = {}
    if error := _serviceable_error(store_settings, address["pincode"]):
        errors["in_pin_code"] = error
    if not address["name"]:
        errors["name"] = "Enter the recipient's name."
    if not address["line1"]:
        errors["address"] = "Enter your house and street."
    if not address["city"]:
        errors["city"] = "Enter your city."
    return address, errors


def parse_text_address(text: str, order: Order, store_settings) -> tuple[dict | None, str | None]:
    """``(address, None)`` from a typed address, or ``(None, message to the buyer)``."""
    raw = (text or "").strip()
    match = PINCODE_IN_TEXT_RE.search(raw)
    example = "\n\nFor example:\nAsha Verma\n12, MG Road\nNear City Mall\nPune, Maharashtra\n411001"
    if match is None:
        return None, "Please include your 6-digit pincode in the address." + example
    pincode = match.group(1) + match.group(2)
    if error := _serviceable_error(store_settings, pincode):
        return None, error
    remainder = raw[: match.start()] + raw[match.end() :]
    separator = "\n" if "\n" in remainder else ","
    parts = [part.strip(" ,.-") for part in remainder.split(separator)]
    parts = [part for part in parts if part and part.lower() not in ("pin", "pincode", "pin code")]
    if separator == "\n":
        # "Pune, Maharashtra" on one line: split city and state.
        expanded = []
        for part in parts:
            pieces = [piece.strip() for piece in part.split(",") if piece.strip()]
            if len(pieces) > 1 and pieces[-1].lower() in _STATES_BY_KEY:
                expanded.extend(pieces)
            else:
                expanded.append(part)
        parts = expanded
    state = ""
    for index, part in enumerate(parts):
        if part.lower() in _STATES_BY_KEY:
            state = _STATES_BY_KEY[part.lower()]
            parts.pop(index)
            break
    contact_name = (order.contact.name or "").strip()
    if len(parts) >= 3:
        name, line1, middle, city = parts[0], parts[1], parts[2:-1], parts[-1]
    elif len(parts) == 2:
        name, line1, middle, city = contact_name, parts[0], [], parts[1]
    else:
        return None, "Please send the full address with your house, street and city." + example
    if not name:
        return None, "Please start the address with the recipient's name." + example
    address = {
        "name": name[:100],
        "phone_e164": (order.contact.phone_e164 or "")[:16],
        "line1": line1[:200],
        "line2": ", ".join(middle)[:200],
        "landmark": "",
        "city": city[:100],
        "state": state,
        "pincode": pincode,
        "country": "IN",
    }
    return address, None


def _accept_address(message: Message, order: Order, address: dict, store_settings) -> None:
    now = timezone.now()
    order.address = address
    order.expires_at = _deadline()
    order.save(update_fields=["address", "expires_at", "updated_at"])
    ShopperAddress.objects.update_or_create(
        workspace_id=order.workspace_id,
        contact_id=order.contact_id,
        defaults={"address": address, "last_used_at": now},
    )
    lifecycle.record_event(
        order,
        OrderEvent.Type.ADDRESS_RECEIVED,
        actor=BUYER,
        detail=f"Deliver to {address['city']} {address['pincode']}.".replace("  ", " "),
        message=message,
    )
    lifecycle.set_status(
        order, Status.AWAITING_PAYMENT_METHOD, actor=BUYER, system=True, message=message
    )
    offer_payment(order, store_settings, idempotency_key=buyer.key(message.pk, "payment"))


def _handle_address_reply(message: Message, conversation: Conversation) -> None:
    order = _lock_checkout(conversation, Status.AWAITING_ADDRESS)
    if order is None:
        _send_stale(conversation, message)
        return
    store_settings = get_store_settings(order.workspace)
    values = _nfm_values(message.payload)
    address, errors = address_from_form(values, order, store_settings)
    if errors:
        request_address(
            order,
            idempotency_key=buyer.key(message.pk, "address"),
            values={k: v for k, v in values.items() if v},
            validation_errors=errors,
        )
        return
    _accept_address(message, order, address, store_settings)


def handle_checkout_text(message: Message) -> bool:
    if message.direction != Message.Direction.INBOUND or message.type != Message.Type.TEXT:
        return False
    if is_offer_code(message.workspace_id, message.text):
        return False  # the offers app answers it
    conversation = _conversation_of(message)
    if not awaiting_address_text(
        message.workspace_id, conversation.contact_id, conversation.phone_number_id
    ):
        return False
    with transaction.atomic():
        conversation = _lock_conversation(conversation.pk)
        if _already_handled(message):
            return True
        order = _lock_checkout(conversation, Status.AWAITING_ADDRESS)
        if order is None or not address_by_text(order.workspace_id, order.contact):
            return False
        store_settings = get_store_settings(order.workspace)
        address, error = parse_text_address(message.text, order, store_settings)
        if error:
            buyer.send_to_buyer(
                order,
                sending.TextContent(error),
                idempotency_key=buyer.key(message.pk, "address"),
            )
            return True
        _accept_address(message, order, address, store_settings)
    return True


def on_address_message_failed(event: MessageDeliveryUpdated) -> None:
    """An ``address_message`` failed with 1026 (unsupported client): ask for typed text."""
    if (
        event.status != Message.Status.FAILED
        or event.error_code != ADDRESS_UNSUPPORTED_ERROR
        or event.source != buyer.SOURCE
        or not event.source_ref.startswith(buyer.SOURCE_REF_PREFIX)
    ):
        return
    failed = Message.objects.filter(pk=event.message_id).only("pk", "payload").first()
    payload = failed.payload if failed is not None else {}
    body = payload.get("interactive") if isinstance(payload, dict) else None
    if not isinstance(body, dict) or body.get("type") != "address_message":
        return
    order_id = _uuid(event.source_ref.removeprefix(buyer.SOURCE_REF_PREFIX))
    if order_id is None:
        return
    with transaction.atomic():
        order = lifecycle.lock_order(order_id, workspace_id=event.workspace_id)
        if order is None or order.status != Status.AWAITING_ADDRESS:
            return
        order.expires_at = _deadline()
        order.save(update_fields=["expires_at", "updated_at"])
        request_address(order, idempotency_key=buyer.key(order.pk, "address_text", failed.pk))


# --- Payment choice -----------------------------------------------------------------------------


def offer_payment(
    order: Order,
    store_settings,
    *,
    idempotency_key: str,
    note: str = "",
    retry: bool = False,
) -> Message | None:
    if order.is_booking:
        return _offer_booking_payment(
            order, store_settings, idempotency_key=idempotency_key, note=note, retry=retry
        )
    options = []
    if online_allowed(order):
        if retry:
            options.append((build_reply_id("chk", "retry", order.pk), "Try again"))
        else:
            options.append((build_reply_id("chk", "pay", order.pk, "online"), "Pay online"))
    cod = cod_allowed(store_settings, order)
    if cod:
        options.append((build_reply_id("chk", "pay", order.pk, "cod"), "Cash on delivery"))
    if not options:
        body = "\n\n".join(
            filter(
                None,
                [
                    note,
                    f"Sorry, {store_display_name(store_settings)} can't take payment for order "
                    f"{order.number} on WhatsApp right now. We'll get in touch with you.",
                ],
            )
        )
        return buyer.send_to_buyer(
            order, sending.TextContent(body), idempotency_key=idempotency_key
        )
    options.append((build_reply_id("chk", "cancel", order.pk), "Cancel order"))
    lines = [note, ""] if note else []
    lines.append(buyer.order_summary(order))
    if order.address:
        lines += ["", "*Deliver to:*", buyer.format_address(order.address)]
    if cod and store_settings.cod_fee_paise:
        lines += ["", f"Cash on delivery adds {format_inr(store_settings.cod_fee_paise)}."]
    lines += ["", "How would you like to pay?"]
    content = interactive.reply_buttons(
        buyer.truncate("\n".join(lines)), options, footer=footer_for(store_settings)
    )
    return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)


def _offer_booking_payment(
    order: Order, store_settings, *, idempotency_key: str, note: str, retry: bool
) -> Message | None:
    """*Pay online* / *Pay at the shop* / *Cancel booking*."""
    options = []
    if online_allowed(order):
        if retry:
            options.append((build_reply_id("chk", "retry", order.pk), "Try again"))
        else:
            options.append((build_reply_id("chk", "pay", order.pk, "online"), "Pay online"))
    if pay_at_shop_allowed(store_settings, order):
        options.append((build_reply_id("chk", "pay", order.pk, "shop"), "Pay at the shop"))
    if not options:
        body = "\n\n".join(
            filter(
                None,
                [
                    note,
                    f"Sorry, {store_display_name(store_settings)} can't take payment for booking "
                    f"{order.number} on WhatsApp right now. We'll get in touch with you.",
                ],
            )
        )
        return buyer.send_to_buyer(
            order, sending.TextContent(body), idempotency_key=idempotency_key
        )
    options.append(_cancel_button(order))
    lines = [note, ""] if note else []
    lines += [buyer.order_summary(order), "", "How would you like to pay?"]
    content = interactive.reply_buttons(
        buyer.truncate("\n".join(lines)), options, footer=footer_for(store_settings)
    )
    return buyer.send_to_buyer(order, content, idempotency_key=idempotency_key)


def _out_of_stock(message: Message, order: Order, exc: OutOfStock, store_settings) -> None:
    lines = []
    for item in exc.items:
        available = item.get("available") or 0
        label = item.get("name") or item.get("sku") or "An item"
        lines.append(
            f"• {label}: {'only ' + str(available) + ' left' if available else 'sold out'}"
        )
    body = "Sorry, some items just ran out:\n" + "\n".join(lines)
    content = interactive.reply_buttons(
        buyer.truncate(body),
        [
            (build_reply_id("chk", "edit", order.pk), "Edit cart"),
            (build_reply_id("chk", "cancel", order.pk), "Cancel order"),
        ],
        footer=footer_for(store_settings),
    )
    buyer.send_to_buyer(order, content, idempotency_key=buyer.key(message.pk, "out_of_stock"))


def _try_reserve(order: Order) -> OutOfStock | None:
    try:
        lifecycle.reserve_stock(order)
    except OutOfStock as exc:
        return exc
    return None


def _choose_online(message: Message, order: Order, store_settings) -> None:
    if not online_allowed(order):
        offer_payment(
            order,
            store_settings,
            idempotency_key=buyer.key(message.pk, "payment"),
            note="Online payment isn't available right now.",
        )
        return
    if (failure := _try_reserve(order)) is not None:
        _out_of_stock(message, order, failure, store_settings)
        return
    order.payment_method = Order.PaymentMethod.ONLINE
    order.cod_fee_paise = 0
    order.total_paise = order_total(order)
    order.checkout_attempt += 1
    order.expires_at = _deadline()
    lifecycle.set_status(order, Status.PENDING_PAYMENT, actor=BUYER, system=True, message=message)
    from .tasks import send_payment_link

    transaction.on_commit(
        partial(send_payment_link.delay, str(order.pk), order.checkout_attempt), robust=True
    )


def _choose_cod(message: Message, order: Order, store_settings) -> None:
    if not cod_allowed(store_settings, order):
        offer_payment(
            order,
            store_settings,
            idempotency_key=buyer.key(message.pk, "payment"),
            note="Cash on delivery isn't available for this order.",
        )
        return
    if (failure := _try_reserve(order)) is not None:
        _out_of_stock(message, order, failure, store_settings)
        return
    order.payment_method = Order.PaymentMethod.COD
    order.payment_status = Order.PaymentStatus.COD_PENDING
    order.cod_fee_paise = store_settings.cod_fee_paise
    order.total_paise = order_total(order)
    lifecycle.set_status(
        order,
        Status.CONFIRMED,
        actor=BUYER,
        system=True,
        detail="Cash on delivery chosen.",
        message=message,
    )
    notifications.notify_buyer(order, Status.CONFIRMED, actor=SYSTEM)


def _choose_shop(message: Message, order: Order, store_settings) -> None:
    if not pay_at_shop_allowed(store_settings, order):
        offer_payment(
            order,
            store_settings,
            idempotency_key=buyer.key(message.pk, "payment"),
            note="Paying at the shop isn't available for this booking.",
        )
        return
    order.payment_method = Order.PaymentMethod.PAY_AT_SHOP
    order.payment_status = Order.PaymentStatus.COD_PENDING
    order.cod_fee_paise = 0
    order.total_paise = order_total(order)
    lifecycle.set_status(
        order,
        Status.REQUESTED,
        actor=BUYER,
        system=True,
        detail="Pay at the shop chosen.",
        message=message,
    )
    _send_request_received(order, idempotency_key=buyer.key(message.pk, "requested"))


# --- Replies ------------------------------------------------------------------------------------


def _chk_confirm(message, conversation, order, reply, store_settings) -> None:
    if order.status != Status.AWAITING_CONFIRMATION:
        _send_stale(conversation, message)
        return
    order.expires_at = _deadline()
    if order.is_booking:
        lifecycle.set_status(order, Status.AWAITING_TIME, actor=BUYER, system=True, message=message)
        ask_day(order, store_settings, idempotency_key=buyer.key(message.pk, "day"))
        return
    lifecycle.set_status(order, Status.AWAITING_ADDRESS, actor=BUYER, system=True, message=message)
    ask_address(order, store_settings, idempotency_key=buyer.key(message.pk, "address"))


def _chk_day(message, conversation, order, reply, store_settings) -> None:
    if order.status != Status.AWAITING_TIME:
        _send_stale(conversation, message)
        return
    day = booking.parse_day_arg(reply.args[1]) if len(reply.args) > 1 else None
    if day is None or not booking.is_bookable_day(store_settings, order.workspace, day):
        ask_day(
            order,
            store_settings,
            idempotency_key=buyer.key(message.pk, "day"),
            note="That day is no longer available. Please pick another one.",
        )
        return
    order.requested_date = day
    order.requested_window = None
    order.expires_at = _deadline()
    order.save(update_fields=["requested_date", "requested_window", "expires_at", "updated_at"])
    ask_window(order, store_settings, day, idempotency_key=buyer.key(message.pk, "window"))


def _chk_win(message, conversation, order, reply, store_settings) -> None:
    if order.status != Status.AWAITING_TIME:
        _send_stale(conversation, message)
        return
    arg = reply.args[1] if len(reply.args) > 1 else ""
    day = order.requested_date
    open_windows = (
        dict(booking.open_windows(store_settings, order.workspace, day))
        if day is not None and booking.is_bookable_day(store_settings, order.workspace, day)
        else {}
    )
    index = int(arg) if arg.isdigit() else None
    if index not in open_windows:
        ask_day(
            order,
            store_settings,
            idempotency_key=buyer.key(message.pk, "day"),
            note="That time is no longer available. Please pick a day again.",
        )
        return
    order.requested_window = dict(open_windows[index])
    order.expires_at = _deadline()
    order.save(update_fields=["requested_window", "expires_at", "updated_at"])
    lifecycle.record_event(
        order,
        OrderEvent.Type.TIME_REQUESTED,
        actor=BUYER,
        detail=f"Asked for {booking.requested_text(order)}.",
        message=message,
        metadata={"date": day.isoformat(), "window": order.requested_window},
    )
    lifecycle.set_status(
        order, Status.AWAITING_PAYMENT_METHOD, actor=BUYER, system=True, message=message
    )
    offer_payment(order, store_settings, idempotency_key=buyer.key(message.pk, "payment"))


def _chk_addr_use(message, conversation, order, reply, store_settings) -> None:
    if order.status != Status.AWAITING_ADDRESS:
        _send_stale(conversation, message)
        return
    address = saved_address(order, store_settings)
    if address is None:
        # Changed since we offered it (pincode no longer served, address cleared): ask afresh.
        request_address(order, idempotency_key=buyer.key(message.pk, "address"))
        return
    _accept_address(message, order, dict(address), store_settings)


def _chk_addr_new(message, conversation, order, reply, store_settings) -> None:
    if order.status != Status.AWAITING_ADDRESS:
        _send_stale(conversation, message)
        return
    order.expires_at = _deadline()
    order.save(update_fields=["expires_at", "updated_at"])
    request_address(order, idempotency_key=buyer.key(message.pk, "address"))


def _chk_edit(message, conversation, order, reply, store_settings) -> None:
    if order.status not in transitions.CHECKOUT_STATUSES:
        _send_stale(conversation, message)
        return
    lifecycle.cancel_order(
        order, actor=BUYER, reason="The buyer went back to edit the cart.", notify_buyer=False
    )
    if order.source == Order.Source.BOT:
        content = interactive.reply_buttons(
            f"No problem. Order {order.number} is cancelled; update your cart and check out again.",
            [_cart_button()],
        )
    else:
        content = sending.TextContent(
            f"No problem. Order {order.number} is cancelled. Open your WhatsApp cart, change it "
            "and send it again."
        )
    buyer.send_to_buyer(order, content, idempotency_key=buyer.key(message.pk, "edit"))


def _chk_pay(message, conversation, order, reply, store_settings) -> None:
    method = reply.args[1] if len(reply.args) > 1 else ""
    methods = ("online", "shop") if order.is_booking else ("online", "cod")
    if order.status != Status.AWAITING_PAYMENT_METHOD or method not in methods:
        _send_stale(conversation, message)
        return
    if method == "online":
        _choose_online(message, order, store_settings)
    elif method == "shop":
        _choose_shop(message, order, store_settings)
    else:
        _choose_cod(message, order, store_settings)


def _chk_retry(message, conversation, order, reply, store_settings) -> None:
    if (
        order.status != Status.AWAITING_PAYMENT_METHOD
        or order.payment_method != Order.PaymentMethod.ONLINE
    ):
        _send_stale(conversation, message)
        return
    _choose_online(message, order, store_settings)


def _chk_cancel(message, conversation, order, reply, store_settings) -> None:
    if order.status not in transitions.CHECKOUT_STATUSES:
        _send_stale(conversation, message)
        return
    lifecycle.cancel_order(order, actor=BUYER, reason="Cancelled by the buyer.", notify_buyer=False)
    content = interactive.reply_buttons(
        f"Your {noun(order)} {order.number} is cancelled.", [_menu_button()]
    )
    buyer.send_to_buyer(order, content, idempotency_key=buyer.key(message.pk, "cancel"))


CHECKOUT_ACTIONS = {
    "confirm": _chk_confirm,
    "addr_use": _chk_addr_use,
    "addr_new": _chk_addr_new,
    "day": _chk_day,
    "win": _chk_win,
    "edit": _chk_edit,
    "pay": _chk_pay,
    "retry": _chk_retry,
    "cancel": _chk_cancel,
}


def handle_checkout_reply(message: Message, reply: ReplyId) -> bool:
    handled_scopes = {
        "chk": set(CHECKOUT_ACTIONS),
        "ord": {"view", "list", *BOOKING_ANSWERS},
        "nfm": {"address_message"},
    }
    if reply.action not in handled_scopes.get(reply.scope, ()):
        return False
    with transaction.atomic():
        conversation = _lock_conversation(message.conversation_id)
        if _already_handled(message):
            return True
        if reply.scope == "nfm":
            _handle_address_reply(message, conversation)
        elif reply.scope == "ord" and reply.action == "list":
            _send_recent_orders(conversation, idempotency_key=buyer.key(message.pk, "orders"))
        elif reply.scope == "ord" and reply.action in BOOKING_ANSWERS:
            _answer_booking(message, conversation, reply)
        elif reply.scope == "ord":
            _view_order(message, conversation, reply)
        else:
            order_id = _uuid(reply.args[0]) if reply.args else None
            order = (
                lifecycle.lock_order(order_id, workspace_id=message.workspace_id)
                if order_id
                else None
            )
            if order is None or order.contact_id != conversation.contact_id:
                _send_stale(conversation, message)
                return True
            store_settings = get_store_settings(order.workspace)
            CHECKOUT_ACTIONS[reply.action](message, conversation, order, reply, store_settings)
    return True


# --- My orders ----------------------------------------------------------------------------------


def _buyer_orders(conversation: Conversation):
    return Order.objects.filter(
        workspace_id=conversation.workspace_id, contact_id=conversation.contact_id
    ).exclude(status=Status.DRAFT)


def send_recent_orders(conversation: Conversation) -> None:
    _send_recent_orders(_conversation_of_pk(conversation.pk), idempotency_key=None)


def _send_recent_orders(conversation: Conversation, *, idempotency_key: str | None) -> None:
    orders = list(_buyer_orders(conversation).order_by("-created_at", "-pk")[:MAX_RECENT_ORDERS])
    store_settings = get_store_settings(conversation.workspace)
    if not orders:
        content = interactive.reply_buttons(
            "You haven't placed any orders with us yet.", [_menu_button()]
        )
    else:
        rows = [
            interactive.ListRow(
                id=build_reply_id("ord", "view", order.pk),
                title=order.number[:24],
                description=(
                    f"{buyer.STATUS_LABELS.get(order.status, order.status)} · "
                    f"{format_inr(order.total_paise)} · "
                    f"{timezone.localtime(order.created_at):%d %b}"
                )[:72],
            )
            for order in orders
        ]
        content = interactive.list_message(
            "Here are your recent orders. Tap one to see its details.",
            "View orders",
            [interactive.ListSection("Recent orders", rows)],
            footer=footer_for(store_settings),
        )
    buyer.send_in_conversation(conversation, content, idempotency_key=idempotency_key)


def _view_order(message: Message, conversation: Conversation, reply: ReplyId) -> None:
    order_id = _uuid(reply.args[0]) if reply.args else None
    order = (
        _buyer_orders(conversation)
        .select_related("workspace", "contact", "phone_number", "conversation")
        .filter(pk=order_id)
        .first()
        if order_id
        else None
    )
    if order is None:
        _send_stale(conversation, message)
        return
    store_settings = get_store_settings(order.workspace)
    body = buyer.status_card(order)
    if order.tracking_url:
        content = interactive.cta_url(
            body, "Track order", order.tracking_url, footer=footer_for(store_settings)
        )
    else:
        content = interactive.reply_buttons(
            body,
            [(build_reply_id("ord", "list"), "My orders")],
            footer=footer_for(store_settings),
        )
    buyer.send_in_conversation(
        conversation,
        content,
        ref=buyer.source_ref(order),
        idempotency_key=buyer.key(message.pk, "view"),
    )


# --- Answers to booking reminders ---------------------------------------------------------------


def _ord_attend(message, conversation, order) -> None:
    now = timezone.now()
    order.attendance_confirmed_at = now
    order.save(update_fields=["attendance_confirmed_at", "updated_at"])
    lifecycle.record_event(
        order,
        OrderEvent.Type.ATTENDANCE_CONFIRMED,
        actor=BUYER,
        detail="The buyer will be there.",
        message=message,
    )
    lifecycle.broadcast_updated(order)
    buyer.send_to_buyer(
        order,
        sending.TextContent(f"Thanks, see you on {booking.appointment_text(order)}."),
        idempotency_key=buyer.key(message.pk, "attend"),
    )


def _ord_resched(message, conversation, order) -> None:
    order.reschedule_requested_at = timezone.now()
    order.save(update_fields=["reschedule_requested_at", "updated_at"])
    lifecycle.record_event(
        order,
        OrderEvent.Type.RESCHEDULE_REQUESTED,
        actor=BUYER,
        detail="The buyer asked to change the time.",
        message=message,
    )
    lifecycle.broadcast_updated(order)
    buyer.send_to_buyer(
        order,
        sending.TextContent("Tell us a day and time that suits you and we'll update your booking."),
        idempotency_key=buyer.key(message.pk, "resched"),
    )


def _ord_bcancel(message, conversation, order) -> None:
    content = interactive.reply_buttons(
        f"Cancel booking {order.number} ({booking.appointment_text(order)})?",
        [
            (build_reply_id("ord", "bcancel_yes", order.pk), "Yes, cancel"),
            (build_reply_id("ord", "bcancel_no", order.pk), "No, keep it"),
        ],
    )
    buyer.send_to_buyer(order, content, idempotency_key=buyer.key(message.pk, "bcancel"))


def _ord_bcancel_yes(message, conversation, order) -> None:
    lifecycle.cancel_order(order, actor=BUYER, reason="Cancelled by the buyer.", notify_buyer=False)
    body = f"Your booking {order.number} is cancelled."
    if order.payment_status == Order.PaymentStatus.PAID:
        body += " The store will refund your payment."
    buyer.send_to_buyer(
        order,
        interactive.reply_buttons(body, [_menu_button()]),
        idempotency_key=buyer.key(message.pk, "bcancel_yes"),
    )


def _ord_bcancel_no(message, conversation, order) -> None:
    buyer.send_to_buyer(
        order,
        sending.TextContent(
            f"Great, your booking stays as it is. See you on {booking.appointment_text(order)}."
        ),
        idempotency_key=buyer.key(message.pk, "bcancel_no"),
    )


BOOKING_ANSWER_ACTIONS = {
    "attend": _ord_attend,
    "resched": _ord_resched,
    "bcancel": _ord_bcancel,
    "bcancel_yes": _ord_bcancel_yes,
    "bcancel_no": _ord_bcancel_no,
}
BOOKING_ANSWERS = frozenset(BOOKING_ANSWER_ACTIONS)


def _answer_booking(message: Message, conversation: Conversation, reply: ReplyId) -> None:
    """A reminder button (template quick reply or session reply button): only for the buyer's
    own booking while it is ``confirmed``; anything else gets the stale text."""
    order_id = _uuid(reply.args[0]) if reply.args else None
    order = lifecycle.lock_order(order_id, workspace_id=message.workspace_id) if order_id else None
    if (
        order is None
        or order.contact_id != conversation.contact_id
        or not order.is_booking
        or order.status != Status.CONFIRMED
    ):
        _send_stale(conversation, message)
        return
    BOOKING_ANSWER_ACTIONS[reply.action](message, conversation, order)


# --- Payment links ------------------------------------------------------------------------------


def create_and_send_payment_link(order_id, attempt: int) -> None:
    """Create the link for checkout attempt ``attempt`` and send it (``orders.send_payment_link``).

    Raises the payments exceptions so the task can retry or fail the attempt.
    """
    order = (
        Order.objects.select_related("workspace", "contact", "phone_number", "conversation")
        .filter(pk=order_id)
        .first()
    )
    if order is None or order.status != Status.PENDING_PAYMENT:
        return
    if order.checkout_attempt != attempt:
        return
    store_settings = get_store_settings(order.workspace)
    link = payment_services.create_payment_link(
        workspace=order.workspace,
        order_id=order.pk,
        reference_id=f"{order.number}-{attempt}",
        amount_paise=order.total_paise,
        description=(
            f"{noun(order).capitalize()} {order.number} from {store_display_name(store_settings)}"
        )[:250],
        customer_name=buyer.buyer_name(order),
        customer_phone_e164=order.contact.phone_e164,
        expire_by=timezone.now() + timedelta(minutes=payment_link_expiry_minutes()),
    )
    if not link.short_url:
        raise PaymentProviderError(
            "The payment link has no URL yet.", provider=link.provider, retryable=True
        )
    with transaction.atomic():
        order = lifecycle.lock_order(order_id)
        if (
            order is None
            or order.status != Status.PENDING_PAYMENT
            or order.checkout_attempt != attempt
        ):
            if order is not None:
                lifecycle.cancel_payment_links_on_commit(order)
            return
        if not order.events.filter(
            type=OrderEvent.Type.PAYMENT_LINK_CREATED, metadata__payment_link_id=str(link.pk)
        ).exists():
            lifecycle.record_event(
                order,
                OrderEvent.Type.PAYMENT_LINK_CREATED,
                actor=SYSTEM,
                detail=f"Payment link {link.reference_id} for {format_inr(link.amount_paise)}.",
                metadata={"payment_link_id": str(link.pk), "attempt": attempt},
            )
        body = (
            f"{noun(order).capitalize()} {order.number}: {format_inr(order.total_paise)}.\n\n"
            "Tap below to pay securely. The link expires in "
            f"{payment_link_expiry_minutes()} minutes."
        )
        content = interactive.cta_url(
            body,
            f"Pay {format_inr(order.total_paise)}"[:20],
            link.short_url,
            footer=footer_for(store_settings),
        )
        buyer.send_to_buyer(
            order, content, idempotency_key=buyer.key(order.pk, "payment_link", attempt)
        )


def payment_link_failed(order_id, attempt: int, *, retryable: bool) -> None:
    """The link for ``attempt`` couldn't be created: release stock and offer the alternatives."""
    with transaction.atomic():
        order = lifecycle.lock_order(order_id)
        if (
            order is None
            or order.status != Status.PENDING_PAYMENT
            or order.checkout_attempt != attempt
        ):
            return
        lifecycle.release_stock(order, actor=SYSTEM, detail="Payment link could not be created.")
        order.expires_at = _deadline()
        lifecycle.set_status(
            order,
            Status.AWAITING_PAYMENT_METHOD,
            actor=SYSTEM,
            system=True,
            detail="The payment link could not be created.",
        )
        store_settings = get_store_settings(order.workspace)
        if retryable:
            offer_payment(
                order,
                store_settings,
                idempotency_key=buyer.key(order.pk, "payment_link_failed", attempt),
                note="Sorry, we couldn't create your payment link just now.",
                retry=True,
            )
            return
        # The seller's gateway account is missing or invalid: online payment can't work.
        body = f"Sorry, online payment isn't available for {noun(order)} {order.number} right now."
        if pay_at_shop_allowed(store_settings, order):
            content = interactive.reply_buttons(
                body + " You can pay at the shop instead.",
                [
                    (build_reply_id("chk", "pay", order.pk, "shop"), "Pay at the shop"),
                    _cancel_button(order),
                ],
                footer=footer_for(store_settings),
            )
        elif cod_allowed(store_settings, order):
            content = interactive.reply_buttons(
                body + " You can pay cash on delivery instead.",
                [
                    (build_reply_id("chk", "pay", order.pk, "cod"), "Cash on delivery"),
                    (build_reply_id("chk", "cancel", order.pk), "Cancel order"),
                ],
                footer=footer_for(store_settings),
            )
        else:
            content = sending.TextContent(body + " The store will get in touch with you.")
        buyer.send_to_buyer(
            order, content, idempotency_key=buyer.key(order.pk, "payment_link_failed", attempt)
        )


# --- Payment events -----------------------------------------------------------------------------


def _cancelled_by_seller(order: Order) -> bool:
    last = (
        order.events.filter(type=OrderEvent.Type.STATUS_CHANGED, to_status=Status.CANCELLED)
        .order_by("-created_at")
        .first()
    )
    return last is not None and last.actor in (
        OrderEvent.Actor.DASHBOARD,
        OrderEvent.Actor.SELLER_WHATSAPP,
    )


def on_payment_link_paid(event) -> None:
    """``PaymentLinkPaid``: confirm the order, revive a closed checkout or flag it."""
    with transaction.atomic():
        order = lifecycle.lock_order(event.order_id, workspace_id=event.workspace_id)
        if order is None:
            return
        link_id = str(event.payment_link_id)
        if order.events.filter(
            type=OrderEvent.Type.PAYMENT_RECEIVED, metadata__payment_link_id=link_id
        ).exists():
            return
        amount = format_inr(event.amount_paise)
        metadata = {
            "payment_link_id": link_id,
            "provider": event.provider,
            "provider_payment_id": event.provider_payment_id,
            "amount_paise": event.amount_paise,
        }
        if order.payment_status in (Order.PaymentStatus.PAID, Order.PaymentStatus.REFUNDED_MANUAL):
            lifecycle.record_event(
                order,
                OrderEvent.Type.PAYMENT_RECEIVED,
                actor=SYSTEM,
                detail=(
                    f"Another {amount} was received for an order that was already paid. Refund "
                    "it in your payment gateway."
                ),
                metadata=metadata,
            )
            return
        lifecycle.record_event(
            order,
            OrderEvent.Type.PAYMENT_RECEIVED,
            actor=SYSTEM,
            detail=f"{amount} received online.",
            metadata=metadata,
        )
        was_cod = order.payment_status == Order.PaymentStatus.COD_PENDING
        order.payment_status = Order.PaymentStatus.PAID
        order.payment_method = Order.PaymentMethod.ONLINE
        order.paid_at = event.paid_at or timezone.now()

        lifecycle.cancel_payment_links_on_commit(order)
        done = transitions.CHECKOUT_DONE.get(order.kind, Status.CONFIRMED)
        if order.status in transitions.CHECKOUT_STATUSES:
            if _try_reserve(order) is None:
                lifecycle.set_status(order, done, actor=SYSTEM, system=True, detail="Paid online.")
                _checkout_done(order, link_id)
            else:
                _flag_paid_order(order, event, "Paid, but some items are out of stock.")
        elif order.status in (Status.EXPIRED, Status.CANCELLED):
            if not _cancelled_by_seller(order) and _try_reserve(order) is None:
                order.cancel_reason = ""
                order.cancelled_at = None
                lifecycle.set_status(
                    order,
                    done,
                    actor=SYSTEM,
                    force=True,
                    detail=(
                        "Paid after the checkout closed; the booking request was received."
                        if order.is_booking
                        else "Paid after the checkout closed; the order was confirmed."
                    ),
                )
                _checkout_done(order, link_id)
            else:
                _flag_paid_order(
                    order,
                    event,
                    f"Paid after the order was {order.status}. Fulfil it or refund the buyer in "
                    "your payment gateway.",
                )
        else:
            order.save()
            detail = "Paid online."
            if was_cod:
                detail = "Paid online after choosing cash on delivery; don't collect cash."
            lifecycle.record_event(order, OrderEvent.Type.NOTE, actor=SYSTEM, detail=detail)
            lifecycle.payment_changed(order, actor=SYSTEM)


def _checkout_done(order: Order, link_id: str) -> None:
    """A paid checkout finished: a booking request is acknowledged, an order confirmed."""
    if order.is_booking:
        _send_request_received(order, idempotency_key=buyer.key(order.pk, "requested", link_id))
    else:
        notifications.notify_buyer(order, Status.CONFIRMED, actor=SYSTEM)


def _flag_paid_order(order: Order, event, detail: str) -> None:
    lifecycle.set_status(
        order,
        Status.NEEDS_ATTENTION,
        actor=SYSTEM,
        system=order.status in transitions.CHECKOUT_STATUSES,
        force=order.status not in transitions.CHECKOUT_STATUSES,
        detail=detail,
    )
    buyer.send_to_buyer(
        order,
        sending.TextContent(
            f"We received your payment for {noun(order)} {order.number}. Some items need a "
            "check by the store, and they'll contact you shortly."
        ),
        idempotency_key=buyer.key(order.pk, "paid_attention", event.payment_link_id),
    )


def on_payment_link_closed(event, *, expired: bool) -> None:
    """``PaymentLinkExpired`` / ``PaymentLinkCancelled`` for the current attempt of a pending
    order: release stock and offer another try or cash on delivery."""
    with transaction.atomic():
        order = lifecycle.lock_order(event.order_id, workspace_id=event.workspace_id)
        if order is None or order.status != Status.PENDING_PAYMENT:
            return
        latest = lifecycle.latest_payment_link(order)
        if latest is None or latest.pk != event.payment_link_id:
            return
        what = "expired" if expired else "was cancelled"
        lifecycle.record_event(
            order,
            OrderEvent.Type.PAYMENT_LINK_EXPIRED,
            actor=SYSTEM,
            detail=f"The payment link {what}.",
            metadata={"payment_link_id": str(event.payment_link_id)},
        )
        lifecycle.release_stock(order, actor=SYSTEM, detail=f"The payment link {what}.")
        order.expires_at = _deadline()
        lifecycle.set_status(order, Status.AWAITING_PAYMENT_METHOD, actor=SYSTEM, system=True)
        offer_payment(
            order,
            get_store_settings(order.workspace),
            idempotency_key=buyer.key(order.pk, "link_closed", event.payment_link_id),
            note=f"The payment link for {noun(order)} {order.number} {what}.",
            retry=True,
        )


# --- Expiry -------------------------------------------------------------------------------------


def expire_checkouts(*, now=None, batch_size: int = 200) -> int:
    """Expire checkouts past ``expires_at``: cancel their links first, then release stock."""
    now = now or timezone.now()
    due = list(
        Order.objects.filter(status__in=transitions.CHECKOUT_STATUSES, expires_at__lt=now)
        .order_by("expires_at")
        .values_list("pk", flat=True)[:batch_size]
    )
    expired = 0
    for order_id in due:
        order = Order.objects.filter(pk=order_id).first()
        if order is None or not _links_closed(order):
            continue
        with transaction.atomic():
            order = lifecycle.lock_order(order_id)
            if (
                order is None
                or order.status not in transitions.CHECKOUT_STATUSES
                or order.expires_at is None
                or order.expires_at >= now
            ):
                continue
            lifecycle.release_stock(order, actor=SYSTEM, detail="The checkout expired.")
            lifecycle.set_status(
                order, Status.EXPIRED, actor=SYSTEM, system=True, detail="The checkout expired."
            )
            buyer.send_to_buyer(
                order,
                sending.TextContent(
                    f'Your checkout for {noun(order)} {order.number} has expired. Send "hi" '
                    "whenever you'd like to shop again."
                ),
                idempotency_key=buyer.key(order.pk, "expired"),
            )
        expired += 1
    return expired


def _links_closed(order: Order) -> bool:
    """Cancel open links before expiring. False keeps the order for the next run: a link that
    turned out paid (its event confirms the order) or a gateway error worth retrying."""
    for link in lifecycle.open_payment_links(order):
        try:
            result = payment_services.cancel_payment_link(link)
        except PaymentProviderError as exc:
            logger.warning("Payment link %s not cancelled before expiry: %s", link.pk, exc)
            if exc.retryable:
                return False
            continue
        except (PaymentAccountMissing, PaymentAccountInvalid) as exc:  # can't cancel it ourselves
            logger.warning("Payment link %s not cancelled before expiry: %s", link.pk, exc)
            continue
        if result is not None and result.status == "paid":
            return False
    return True


OFFER_CHECKOUT_STATUSES = (
    Status.AWAITING_CONFIRMATION,
    Status.AWAITING_ADDRESS,
    Status.AWAITING_TIME,
    Status.AWAITING_PAYMENT_METHOD,
)


def apply_offer_to_active_checkout(conversation_id) -> bool:
    """Apply a newly claimed offer to the contact's open checkout (services-and-offers contract,
    "Offers hook in checkout"). In ``awaiting_payment_method`` the payment choice is sent again
    with the new total. Returns whether an offer was applied."""
    if not Conversation.objects.filter(pk=conversation_id).exists():
        return False
    with transaction.atomic():
        conversation = _lock_conversation(conversation_id)
        order = _lock_checkout(conversation, *OFFER_CHECKOUT_STATUSES)
        if order is None or not _apply_offer(order):
            return False
        lifecycle.broadcast_updated(order)
        if order.status == Status.AWAITING_PAYMENT_METHOD:
            offer_payment(
                order,
                get_store_settings(order.workspace),
                idempotency_key=buyer.key(
                    order.pk, "offer", order.offer_claim_id, order.discount_paise
                ),
                note=(
                    f"Offer {order.offer_code} applied: you save "
                    f"{format_inr(order.discount_paise)}."
                ),
            )
    return True
