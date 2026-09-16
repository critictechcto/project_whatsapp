"""Buyer checkout on WhatsApp: cart to order, address, payment choice, stale replies, My orders."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.factories import ProductFactory
from apps.catalog.services import DroppedLine
from apps.contacts.factories import ContactFactory
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Message
from apps.orders import checkout, services
from apps.orders.exceptions import CheckoutRejected
from apps.orders.factories import OrderFactory, OrderItemFactory, ShopperAddressFactory
from apps.orders.models import Order, ShopperAddress
from common import events
from common.commerce import build_reply_id

from .helpers import (
    VALID_FORM,
    content_text,
    delivery_failed_event,
    event_types,
    interactive_type,
    last_outbound,
    outbound,
    press,
    priced_cart,
    recorded_event,
    refresh,
    reply_ids,
    start,
    submit_address,
    typed,
)

pytestmark = pytest.mark.django_db


def pay(order, method: str) -> str:
    return build_reply_id("chk", "pay", order.pk, method)


@pytest.fixture
def foreign_conversation(workspace, store, number):
    contact = ContactFactory(workspace=workspace, phone_e164="+14155550123", name="Sam Lee")
    return ConversationFactory(
        workspace=workspace, contact=contact, phone_number=number, window_open=True
    )


# --- Starting a checkout ------------------------------------------------------------------------


def test_start_checkout_snapshots_items_and_asks_for_the_address(conversation, store, product):
    store.shipping_fee_paise = 4900
    store.free_shipping_above_paise = 99900
    store.save()
    other = ProductFactory(workspace=conversation.workspace, name="Soan Papdi", price_paise=19900)

    order = start(conversation, (product, 2), (other, 1))

    assert order.status == Order.Status.AWAITING_ADDRESS
    assert order.number == "SS-1001"
    assert order.conversation_id == conversation.pk
    assert order.phone_number_id == conversation.phone_number_id
    assert (order.item_count, order.subtotal_paise, order.shipping_paise, order.total_paise) == (
        3,
        69700,
        4900,
        74600,
    )
    assert order.expires_at > timezone.now() + timedelta(minutes=30)
    items = [
        (item.product_id, item.sku, item.name, item.unit_price_paise, item.quantity)
        for item in order.items.order_by("position")
    ]
    assert items == [
        (product.pk, product.sku, product.name, 24900, 2),
        (other.pk, other.sku, other.name, 19900, 1),
    ]
    assert event_types(order) == ["created"]
    message = last_outbound(conversation.contact)
    assert interactive_type(message) == "address_message"
    assert (message.source, message.source_ref) == ("commerce", f"order:{order.pk}")


def test_free_shipping_above_the_threshold(conversation, store, product):
    store.shipping_fee_paise = 4900
    store.free_shipping_above_paise = 40000
    store.save()

    order = start(conversation, (product, 2))

    assert (order.shipping_paise, order.total_paise) == (0, 49800)


def test_address_form_is_prefilled_from_the_saved_address(conversation, product):
    ShopperAddressFactory(workspace=conversation.workspace, contact=conversation.contact)

    start(conversation, (product, 1))

    form = json.dumps(last_outbound(conversation.contact).payload["interactive"])
    assert "411001" in form
    assert "12, MG Road" in form


def test_price_change_needs_confirmation(conversation, product):
    order = start(
        conversation,
        (product, 2),
        source="native_cart",
        source_wamid="wamid.CART1",
        quoted_total_paise=45000,
    )

    assert order.status == Order.Status.AWAITING_CONFIRMATION
    assert event_types(order) == ["created", "price_changed"]
    ids = reply_ids(last_outbound(conversation.contact))
    assert ids == [
        build_reply_id("chk", "confirm", order.pk),
        build_reply_id("chk", "edit", order.pk),
    ]

    press(conversation, build_reply_id("chk", "confirm", order.pk))

    assert refresh(order).status == Order.Status.AWAITING_ADDRESS
    assert interactive_type(last_outbound(conversation.contact)) == "address_message"


def test_matching_quote_goes_straight_to_the_address(conversation, product):
    order = start(
        conversation,
        (product, 2),
        source="native_cart",
        source_wamid="wamid.CART2",
        quoted_total_paise=49800,
    )

    assert order.status == Order.Status.AWAITING_ADDRESS


def test_edit_cart_cancels_the_checkout(conversation, product):
    order = start(conversation, (product, 2), quoted_total_paise=45000)

    press(conversation, build_reply_id("chk", "edit", order.pk))

    order = refresh(order)
    assert order.status == Order.Status.CANCELLED
    assert build_reply_id("shop", "cart") in reply_ids(last_outbound(conversation.contact))


def test_start_checkout_is_idempotent_on_source_wamid(conversation, product):
    first = start(conversation, (product, 1), source="native_cart", source_wamid="wamid.SAME")
    sent = Message.objects.filter(direction=Message.Direction.OUTBOUND).count()

    again = start(conversation, (product, 1), source="native_cart", source_wamid="wamid.SAME")

    assert again.pk == first.pk
    assert Order.objects.count() == 1
    assert Message.objects.filter(direction=Message.Direction.OUTBOUND).count() == sent


def test_the_inbound_message_that_started_checkout_links_to_the_order(conversation, product):
    cart_message = MessageFactory(
        conversation=conversation, inbound=True, type=Message.Type.ORDER, wamid="wamid.CART"
    )
    unrelated = MessageFactory(conversation=conversation, inbound=True, wamid="wamid.OTHER")

    order = start(conversation, (product, 1), source="native_cart", source_wamid="wamid.CART")

    cart_message.refresh_from_db()
    unrelated.refresh_from_db()
    assert cart_message.source_ref == f"order:{order.pk}"
    assert cart_message.source == Message.Source.INBOUND
    assert unrelated.source_ref == ""


def test_new_checkout_supersedes_the_active_one(
    conversation,
    product,
    online,
    payment_links,
    cancelled_links,
    django_capture_on_commit_callbacks,
):
    product.stock_qty = 5
    product.save()
    first = start(conversation, (product, 2))
    submit_address(conversation)
    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, pay(first, "online"))
    product.refresh_from_db()
    assert (refresh(first).status, product.stock_qty) == (Order.Status.PENDING_PAYMENT, 3)

    with django_capture_on_commit_callbacks(execute=True):
        second = start(conversation, (product, 1))

    first = refresh(first)
    product.refresh_from_db()
    assert first.status == Order.Status.CANCELLED
    assert first.cancel_reason == "Replaced by a new checkout."
    assert not first.stock_reserved
    assert product.stock_qty == 5
    assert cancelled_links == [first.payment_links.get().pk]
    assert second.status == Order.Status.AWAITING_ADDRESS
    assert any(
        first.number in message.text and "replaced" in message.text
        for message in outbound(conversation.contact)
    )


def test_below_minimum_order_is_rejected(conversation, store, product):
    store.min_order_paise = 50000
    store.save()

    with pytest.raises(CheckoutRejected) as exc:
        start(conversation, (product, 1))

    assert exc.value.reason == "below_minimum"
    assert not Order.objects.exists()
    assert "₹500.00" in content_text(last_outbound(conversation.contact))


def test_cart_with_nothing_orderable_is_rejected_with_the_reasons(conversation):
    gone = DroppedLine(
        sku="SKU-GONE", name="Rasgulla Tin", reason="out_of_stock", requested=2, available=0
    )

    with pytest.raises(CheckoutRejected) as exc:
        services.start_checkout(
            workspace=conversation.workspace,
            conversation=conversation,
            cart=priced_cart(dropped=[gone]),
            source="native_cart",
            source_wamid="wamid.EMPTY",
        )

    assert exc.value.reason == "empty_cart"
    assert "Rasgulla Tin is out of stock" in content_text(last_outbound(conversation.contact))


def test_dropped_lines_are_explained(conversation, product):
    capped = DroppedLine(
        sku=product.sku, name="Kaju Katli", reason="quantity_capped", requested=9, available=5
    )

    order = start(conversation, (product, 5), dropped=[capped])

    assert order.status == Order.Status.AWAITING_ADDRESS
    assert any(
        "Kaju Katli: only 5 can be ordered" in content_text(message)
        for message in outbound(conversation.contact)
    )


# --- Address ------------------------------------------------------------------------------------


def test_address_form_moves_to_the_payment_choice(conversation, store, product, online):
    store.cod_enabled = True
    store.save()
    order = start(conversation, (product, 2))

    message = submit_address(conversation)

    order = refresh(order)
    assert order.status == Order.Status.AWAITING_PAYMENT_METHOD
    assert order.address == {
        "name": "Asha Verma",
        "phone_e164": "+919876543210",
        "line1": "MG Road",
        "line2": "12, Lotus Apartments",
        "landmark": "Camp",
        "city": "Pune",
        "state": "Maharashtra",
        "pincode": "411001",
        "country": "IN",
    }
    saved = ShopperAddress.objects.get(contact=conversation.contact)
    assert saved.address == order.address
    assert order.events.get(type="address_received").message_id == message.pk
    assert reply_ids(last_outbound(conversation.contact)) == [
        pay(order, "online"),
        pay(order, "cod"),
        build_reply_id("chk", "cancel", order.pk),
    ]


@pytest.mark.parametrize(
    ("cod_enabled", "cod_max_order_paise", "expected"),
    [(False, None, []), (True, None, ["cod"]), (True, 40000, [])],
)
def test_cash_on_delivery_is_offered_by_the_store_rules(
    conversation, store, product, cod_enabled, cod_max_order_paise, expected
):
    store.cod_enabled = cod_enabled
    store.cod_max_order_paise = cod_max_order_paise
    store.save()
    order = start(conversation, (product, 2))

    submit_address(conversation)

    ids = reply_ids(last_outbound(conversation.contact))
    assert [method for method in ("online", "cod") if pay(order, method) in ids] == expected


def test_invalid_pincode_resends_the_form_with_errors(conversation, product):
    order = start(conversation, (product, 1))

    submit_address(conversation, {**VALID_FORM, "in_pin_code": "4110"})

    assert refresh(order).status == Order.Status.AWAITING_ADDRESS
    form = last_outbound(conversation.contact).payload["interactive"]
    assert form["type"] == "address_message"
    assert "validation_errors" in json.dumps(form)
    assert "6-digit pincode" in json.dumps(form)
    assert not ShopperAddress.objects.exists()


def test_pincode_outside_the_serviceable_list_is_rejected(conversation, store, product):
    store.serviceable_pincodes = ["560034"]
    store.save()
    order = start(conversation, (product, 1))

    submit_address(conversation)

    assert refresh(order).status == Order.Status.AWAITING_ADDRESS
    form = last_outbound(conversation.contact).payload["interactive"]
    assert "deliver to this pincode" in json.dumps(form)


def test_non_indian_buyer_types_the_address(foreign_conversation, product):
    conversation = foreign_conversation
    order = start(conversation, (product, 1))
    prompt = last_outbound(conversation.contact)
    assert prompt.type == Message.Type.TEXT
    assert order.number in prompt.text

    message = typed(
        conversation, "Asha Verma\n12, MG Road\nNear City Mall\nPune, Maharashtra\n411001"
    )

    assert checkout.claim_awaited_text(recorded_event(message)) is True
    assert services.handle_checkout_text(message) is True
    order = refresh(order)
    assert order.status == Order.Status.AWAITING_PAYMENT_METHOD
    address = order.address
    assert (address["name"], address["line1"], address["line2"]) == (
        "Asha Verma",
        "12, MG Road",
        "Near City Mall",
    )
    assert (address["city"], address["state"], address["pincode"]) == (
        "Pune",
        "Maharashtra",
        "411001",
    )


def test_typed_address_without_a_pincode_asks_again(foreign_conversation, product):
    conversation = foreign_conversation
    order = start(conversation, (product, 1))

    assert services.handle_checkout_text(typed(conversation, "12 MG Road, Pune")) is True

    assert refresh(order).status == Order.Status.AWAITING_ADDRESS
    assert "6-digit pincode" in last_outbound(conversation.contact).text


def test_text_is_not_claimed_while_the_address_form_is_used(conversation, product):
    start(conversation, (product, 1))
    message = typed(conversation, "hello")

    assert checkout.claim_awaited_text(recorded_event(message)) is False
    assert services.handle_checkout_text(message) is False


def test_address_form_failure_1026_falls_back_to_typed_text(conversation, product):
    order = start(conversation, (product, 1))
    form = last_outbound(conversation.contact)
    Message.objects.filter(pk=form.pk).update(status=Message.Status.FAILED, error_code="1026")

    events.emit(events.message_delivery_updated, delivery_failed_event(form))

    prompt = last_outbound(conversation.contact)
    assert prompt.type == Message.Type.TEXT
    assert "type the full address" in prompt.text
    message = typed(conversation, "Asha Verma\n12, MG Road\nPune\n411001")
    assert checkout.claim_awaited_text(recorded_event(message)) is True
    assert services.handle_checkout_text(message) is True
    assert refresh(order).status == Order.Status.AWAITING_PAYMENT_METHOD


# --- Payment choice -----------------------------------------------------------------------------


def test_online_payment_reserves_stock_and_sends_the_link(
    conversation, product, online, payment_links, django_capture_on_commit_callbacks
):
    product.stock_qty = 5
    product.save()
    order = start(conversation, (product, 2))
    submit_address(conversation)

    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, pay(order, "online"))

    order = refresh(order)
    product.refresh_from_db()
    assert (order.status, order.payment_method) == (Order.Status.PENDING_PAYMENT, "online")
    assert order.stock_reserved
    assert order.checkout_attempt == 1
    assert product.stock_qty == 3
    [call] = payment_links
    assert call["reference_id"] == f"{order.number}-1"
    assert call["amount_paise"] == order.total_paise
    assert call["customer_phone_e164"] == conversation.contact.phone_e164
    remaining = call["expire_by"] - timezone.now()
    assert timedelta(minutes=29) < remaining <= timedelta(minutes=30)
    link = order.payment_links.get()
    message = last_outbound(conversation.contact)
    assert interactive_type(message) == "cta_url"
    assert link.short_url in json.dumps(message.payload)
    assert "payment_link_created" in event_types(order)


def test_online_payment_needs_a_ready_gateway(conversation, store, product):
    store.cod_enabled = True
    store.save()
    order = start(conversation, (product, 1))
    submit_address(conversation)
    assert pay(order, "online") not in reply_ids(last_outbound(conversation.contact))

    press(conversation, pay(order, "online"))

    assert refresh(order).status == Order.Status.AWAITING_PAYMENT_METHOD
    assert "Online payment isn't available" in content_text(last_outbound(conversation.contact))


def test_cash_on_delivery_confirms_with_the_fee(conversation, store, product):
    store.cod_enabled = True
    store.cod_fee_paise = 2000
    store.shipping_fee_paise = 4900
    store.save()
    order = start(conversation, (product, 2))
    submit_address(conversation)

    press(conversation, pay(order, "cod"))

    order = refresh(order)
    assert order.status == Order.Status.CONFIRMED
    assert (order.payment_method, order.payment_status) == ("cod", "cod_pending")
    assert (order.cod_fee_paise, order.total_paise) == (2000, 49800 + 4900 + 2000)
    assert order.confirmed_at is not None
    assert order.expires_at is None
    assert order.stock_reserved
    assert "notification_sent" in event_types(order)


def test_out_of_stock_at_payment_offers_edit_cart(conversation, store, product):
    store.cod_enabled = True
    store.save()
    product.stock_qty = 1
    product.save()
    order = start(conversation, (product, 2))
    submit_address(conversation)

    press(conversation, pay(order, "cod"))

    order = refresh(order)
    product.refresh_from_db()
    assert order.status == Order.Status.AWAITING_PAYMENT_METHOD
    assert not order.stock_reserved
    assert product.stock_qty == 1
    message = last_outbound(conversation.contact)
    assert build_reply_id("chk", "edit", order.pk) in reply_ids(message)
    assert "only 1 left" in content_text(message)


# --- Stale and repeated replies -----------------------------------------------------------------


def test_stale_buttons_are_refused(conversation, store, product):
    store.cod_enabled = True
    store.save()
    order = start(conversation, (product, 1))

    press(conversation, pay(order, "cod"))

    assert refresh(order).status == Order.Status.AWAITING_ADDRESS
    message = last_outbound(conversation.contact)
    assert "no longer available" in content_text(message)
    assert build_reply_id("shop", "menu") in reply_ids(message)


def test_buttons_for_another_buyers_order_are_refused(workspace, number, conversation, product):
    other = ConversationFactory(workspace=workspace, phone_number=number, window_open=True)
    order = start(other, (product, 1))

    press(conversation, build_reply_id("chk", "cancel", order.pk))

    assert refresh(order).status == Order.Status.AWAITING_ADDRESS
    assert "no longer available" in content_text(last_outbound(conversation.contact))


def test_a_redelivered_reply_is_handled_once(conversation, store, product):
    store.cod_enabled = True
    store.save()
    order = start(conversation, (product, 1))
    submit_address(conversation)
    message = press(conversation, pay(order, "cod"))
    sent = Message.objects.filter(direction=Message.Direction.OUTBOUND).count()

    press(conversation, pay(order, "cod"), message=message)

    assert Message.objects.filter(direction=Message.Direction.OUTBOUND).count() == sent
    assert order.events.filter(type="status_changed", to_status="confirmed").count() == 1


def test_buyer_cancels_the_checkout(conversation, product):
    order = start(conversation, (product, 1))

    press(conversation, build_reply_id("chk", "cancel", order.pk))

    order = refresh(order)
    assert order.status == Order.Status.CANCELLED
    assert order.events.get(type="status_changed").actor == "buyer"


# --- My orders ----------------------------------------------------------------------------------


def test_my_orders_lists_the_latest_ten(conversation):
    for _ in range(11):
        OrderFactory(
            workspace=conversation.workspace,
            contact=conversation.contact,
            phone_number=conversation.phone_number,
        )

    services.send_recent_orders(conversation)

    message = last_outbound(conversation.contact)
    assert interactive_type(message) == "list"
    rows = [reply for reply in reply_ids(message) if reply.startswith("upc:ord:view:")]
    assert len(rows) == 10


def test_order_card_shows_status_and_tracking(conversation):
    order = OrderFactory(
        workspace=conversation.workspace,
        contact=conversation.contact,
        phone_number=conversation.phone_number,
        status=Order.Status.SHIPPED,
        courier_name="Delhivery",
        awb_number="DL1",
        tracking_url="https://track.example.com/DL1",
    )
    OrderItemFactory(order=order)

    press(conversation, build_reply_id("ord", "view", order.pk))

    message = last_outbound(conversation.contact)
    assert interactive_type(message) == "cta_url"
    text = content_text(message)
    assert order.number in text
    assert "Shipped" in text
    assert "https://track.example.com/DL1" in text


def test_order_card_of_another_buyer_is_refused(workspace, number, conversation):
    other = ConversationFactory(workspace=workspace, phone_number=number)
    order = OrderFactory(workspace=workspace, contact=other.contact, phone_number=number)

    press(conversation, build_reply_id("ord", "view", order.pk))

    assert "no longer available" in content_text(last_outbound(conversation.contact))
