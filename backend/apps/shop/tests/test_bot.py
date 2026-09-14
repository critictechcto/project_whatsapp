"""The buyer bot in bot mode: menu, browsing, cart, checkout hand-off and stale ids."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing import services as billing_services
from apps.catalog.factories import CollectionFactory, MetaCatalogFactory, ProductFactory
from apps.catalog.models import Product
from apps.catalog.services import OutOfStock
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Message
from apps.orders.models import StoreSettings
from apps.shop import content, services
from apps.shop.content import shop_id
from apps.shop.factories import BotSessionFactory
from apps.shop.models import BotSession
from apps.whatsapp.factories import PhoneNumberFactory
from common.commerce import ReplyId

from .helpers import (
    assert_message_limits,
    body_of,
    button_ids,
    button_titles,
    interactive_of,
    row_ids,
    rows,
)

UNAVAILABLE = content.UNAVAILABLE


def session_of(conversation) -> BotSession:
    return BotSession.objects.get(conversation=conversation)


def assert_unavailable_menu(message: Message) -> None:
    assert body_of(message).startswith(UNAVAILABLE)
    assert button_ids(message) == [shop_id("browse"), shop_id("orders"), shop_id("talk")]


# --- Full navigation ----------------------------------------------------------------------------


def test_menu_to_checkout(
    buyer, store, sweets, product, workspace, conversation, orders_calls, settings
):
    settings.PUBLIC_MEDIA_BASE_URL = "https://media.example.com"
    product.image = "catalog/products/kaju.jpg"
    product.position = 0
    product.save()
    for i in range(11):
        ProductFactory(workspace=workspace, collection=sweets, position=100 + i)

    # Menu
    assert buyer.says("Hi") is True
    [menu] = buyer.new_replies()
    assert body_of(menu) == "Namaste! Welcome to Sharma Sweets."
    assert button_ids(menu) == [shop_id("browse"), shop_id("orders"), shop_id("talk")]
    assert button_titles(menu) == ["Shop now", "My orders", "Talk to us"]
    assert interactive_of(menu)["footer"] == {"text": "Powered by UpChatz"}

    # Collections
    buyer.taps(shop_id("browse"))
    [collections] = buyer.new_replies()
    assert interactive_of(collections)["type"] == "list"
    assert rows(collections) == [
        {"id": shop_id("col", sweets.pk, 0), "title": "Sweets", "description": "Fresh every day"}
    ]

    # Products, first page: 9 products and "More products"
    buyer.taps(shop_id("col", sweets.pk, 0))
    [page_one] = buyer.new_replies()
    page_rows = rows(page_one)
    assert len(page_rows) == 10
    assert page_rows[0] == {
        "id": shop_id("prod", product.pk),
        "title": "Kaju Katli 500g",
        "description": "₹499.00 (MRP ₹599.00)",
    }
    assert page_rows[-1]["id"] == shop_id("col", sweets.pk, 9)
    assert page_rows[-1]["title"] == "More products"

    # Second page
    buyer.taps(shop_id("col", sweets.pk, 9))
    [page_two] = buyer.new_replies()
    assert len(rows(page_two)) == 3
    assert all(row_id.startswith("upc:shop:prod:") for row_id in row_ids(page_two))
    assert "Products 10-12" in body_of(page_two)

    # Product card
    buyer.taps(shop_id("prod", product.pk))
    [card] = buyer.new_replies()
    card_data = interactive_of(card)
    assert card_data["header"] == {
        "type": "image",
        "image": {"link": "https://media.example.com/catalog/products/kaju.jpg"},
    }
    assert body_of(card).startswith("*Kaju Katli 500g*\n₹499.00 (MRP ₹599.00)")
    assert button_ids(card) == [
        shop_id("add", product.pk, 1),
        shop_id("qty", product.pk),
        shop_id("col", sweets.pk, 9),  # back to the page the buyer came from
    ]
    assert button_titles(card) == ["Add to cart", "Change qty", "Back"]

    # Quantity list, then a typed quantity
    buyer.taps(shop_id("qty", product.pk))
    [quantities] = buyer.new_replies()
    assert row_ids(quantities) == [shop_id("add", product.pk, n) for n in range(1, 11)]
    assert session_of(conversation).state == BotSession.State.AWAITING_QUANTITY

    assert buyer.says("3") is True
    [added] = buyer.new_replies()
    assert body_of(added) == "Added 3 x Kaju Katli 500g to your cart.\nCart: 3 items · ₹1,497.00"
    assert button_ids(added) == [
        shop_id("checkout"),
        shop_id("col", sweets.pk, 9),
        shop_id("cart"),
    ]
    assert button_titles(added) == ["Checkout", "Keep shopping", "View cart"]
    session = session_of(conversation)
    assert session.state == BotSession.State.IDLE
    assert session.cart == [{"product_id": str(product.pk), "quantity": 3}]

    # Add one more from the card
    buyer.taps(shop_id("add", product.pk, 1))
    [added_again] = buyer.new_replies()
    assert "Cart: 4 items · ₹1,996.00" in body_of(added_again)

    # Cart
    buyer.taps(shop_id("cart"))
    [cart] = buyer.new_replies()
    assert body_of(cart) == "*Your cart*\n4 x Kaju Katli 500g — ₹1,996.00\n\nSubtotal: ₹1,996.00"
    assert button_ids(cart) == [shop_id("checkout"), shop_id("clear"), shop_id("browse")]

    # Checkout hand-off
    assert orders_calls.start_checkout == []
    buyer.taps(shop_id("checkout"))
    [call] = orders_calls.start_checkout
    assert set(call) == {"workspace", "conversation", "cart", "source"}
    assert call["workspace"].pk == workspace.pk
    assert call["conversation"].pk == conversation.pk
    assert call["source"] == "bot"
    assert [(line.product.pk, line.quantity) for line in call["cart"].lines] == [(product.pk, 4)]
    assert call["cart"].subtotal_paise == 4 * 49900
    assert buyer.new_replies() == []  # orders sends the next step

    replies = buyer.replies()
    assert {(m.source, m.source_ref) for m in replies} == {(Message.Source.AUTOMATION, "shop")}
    for reply in replies:
        assert_message_limits(reply)
    assert session_of(conversation).expires_at == (
        session_of(conversation).last_message_at + timedelta(hours=24)
    )


def test_menu_without_welcome_message_or_footer(buyer, store):
    store.welcome_message = ""
    store.powered_by_footer = False
    store.menu_keywords = ["Namaste"]
    store.save()

    assert buyer.says("hi") is False
    assert buyer.says("  NAMASTE ") is True

    [menu] = buyer.replies()
    assert body_of(menu) == "Welcome to Sharma Sweets! Tap *Shop now* to browse our products."
    assert "footer" not in interactive_of(menu)


def test_browse_lists_other_products_and_caps_rows(buyer, store, workspace):
    collections = [CollectionFactory(workspace=workspace, position=i) for i in range(12)]
    for collection in collections:
        ProductFactory(workspace=workspace, collection=collection)
    loose = ProductFactory(workspace=workspace, collection=None)

    buyer.taps(shop_id("browse"))
    [listing] = buyer.new_replies()
    ids = row_ids(listing)
    assert len(ids) == 10
    assert ids[:9] == [shop_id("col", c.pk, 0) for c in collections[:9]]
    assert ids[9] == shop_id("col", "other", 0)

    buyer.taps(shop_id("col", "other", 0))
    [other] = buyer.new_replies()
    assert row_ids(other) == [shop_id("prod", loose.pk)]


def test_browse_without_collections_shows_all_products(buyer, store, workspace):
    first = ProductFactory(workspace=workspace, position=1)
    ProductFactory(workspace=workspace, position=2, is_active=False)

    buyer.taps(shop_id("browse"))

    [listing] = buyer.replies()
    assert row_ids(listing) == [shop_id("prod", first.pk)]
    assert body_of(listing).startswith("*All products*")


def test_browse_without_products(buyer, store):
    buyer.taps(shop_id("browse"))

    [reply] = buyer.replies()
    assert reply.type == Message.Type.TEXT
    assert reply.text == content.NO_PRODUCTS


def test_native_catalog_mode_sends_the_catalog(buyer, store, workspace, number, product):
    store.shop_mode = StoreSettings.ShopMode.NATIVE_CATALOG
    store.save()
    MetaCatalogFactory(waba=number.waba)
    product.meta_sync_status = Product.SyncStatus.SYNCED
    product.save()

    buyer.taps(shop_id("browse"))

    [reply] = buyer.replies()
    data = interactive_of(reply)
    assert data["type"] == "catalog_message"
    assert data["action"] == {
        "name": "catalog_message",
        "parameters": {"thumbnail_product_retailer_id": product.sku},
    }
    assert data["footer"] == {"text": "Powered by UpChatz"}


def test_native_mode_without_a_connected_catalog_falls_back_to_bot_lists(
    buyer, store, sweets, product
):
    store.shop_mode = StoreSettings.ShopMode.NATIVE_CATALOG
    store.save()

    buyer.taps(shop_id("browse"))

    [reply] = buyer.replies()
    assert row_ids(reply) == [shop_id("col", sweets.pk, 0)]


# --- Quantities and cart ------------------------------------------------------------------------


def test_typed_quantity_out_of_range_asks_again(buyer, store, product, conversation):
    product.max_qty_per_order = 5
    product.save()

    buyer.taps(shop_id("qty", product.pk))
    [quantities] = buyer.new_replies()
    assert row_ids(quantities) == [shop_id("add", product.pk, n) for n in range(1, 6)]

    buyer.says("7")
    [retry] = buyer.new_replies()
    assert retry.text == "Please type a number from 1 to 5."
    assert session_of(conversation).state == BotSession.State.AWAITING_QUANTITY

    buyer.says("5")
    [added] = buyer.new_replies()
    assert body_of(added).startswith("Added 5 x")
    assert session_of(conversation).cart == [{"product_id": str(product.pk), "quantity": 5}]


def test_large_quantities_can_be_typed(buyer, store, product, conversation):
    product.max_qty_per_order = 20
    product.save()

    buyer.taps(shop_id("qty", product.pk))
    [quantities] = buyer.new_replies()
    assert len(rows(quantities)) == 10
    assert "type a number from 1 to 20" in body_of(quantities)

    buyer.says("15")
    assert session_of(conversation).cart == [{"product_id": str(product.pk), "quantity": 15}]


def test_adding_is_capped_at_stock(buyer, store, product, conversation):
    product.stock_qty = 2
    product.save()

    buyer.taps(shop_id("add", product.pk, 5))
    [capped] = buyer.new_replies()
    assert body_of(capped).startswith(
        "Added 2 x Kaju Katli 500g to your cart. You can order at most 2."
    )

    buyer.taps(shop_id("add", product.pk, 1))
    [full] = buyer.new_replies()
    assert body_of(full).startswith("You already have 2 x Kaju Katli 500g in your cart")
    assert session_of(conversation).cart == [{"product_id": str(product.pk), "quantity": 2}]


def test_other_text_while_awaiting_a_quantity_goes_to_checkout(
    buyer, store, product, conversation, orders_calls
):
    buyer.taps(shop_id("qty", product.pk))
    orders_calls.text_result = True

    assert buyer.says("12, MG Road, Pune") is True

    assert orders_calls.texts == [buyer.last]
    assert session_of(conversation).state == BotSession.State.IDLE


def test_unclaimed_text_is_forwarded_to_checkout(buyer, store, orders_calls):
    assert buyer.says("where is my parcel?") is False

    assert orders_calls.texts == [buyer.last]
    assert buyer.replies() == []


def test_cart_drops_unavailable_items(buyer, store, workspace, product, conversation):
    gone = ProductFactory(workspace=workspace, name="Soan Papdi")
    BotSessionFactory(
        conversation=conversation,
        cart=[
            {"product_id": str(product.pk), "quantity": 1},
            {"product_id": str(gone.pk), "quantity": 2},
        ],
    )
    gone.availability = Product.Availability.OUT_OF_STOCK
    gone.save()

    buyer.taps(shop_id("cart"))

    [cart] = buyer.replies()
    assert body_of(cart) == (
        "*Your cart*\n1 x Kaju Katli 500g — ₹499.00\n\nSubtotal: ₹499.00\n\n"
        "Soan Papdi is out of stock and was removed."
    )
    assert session_of(conversation).cart == [{"product_id": str(product.pk), "quantity": 1}]


def test_clear_cart(buyer, store, product, conversation):
    buyer.taps(shop_id("add", product.pk, 2))
    buyer.taps(shop_id("clear"))

    assert session_of(conversation).cart == []
    assert body_of(buyer.last_reply()) == "Your cart is now empty."
    assert button_ids(buyer.last_reply()) == [shop_id("browse"), shop_id("talk")]


def test_checkout_with_an_empty_cart(buyer, store, orders_calls):
    buyer.taps(shop_id("checkout"))

    assert orders_calls.start_checkout == []
    assert body_of(buyer.last_reply()) == "Your cart is empty, so there's nothing to check out yet."


def test_checkout_when_every_item_is_gone(buyer, store, product, conversation, orders_calls):
    buyer.taps(shop_id("add", product.pk, 1))
    product.is_active = False
    product.save()

    buyer.taps(shop_id("checkout"))

    assert orders_calls.start_checkout == []
    assert body_of(buyer.last_reply()).startswith("The items in your cart are no longer available")
    assert session_of(conversation).cart == []


def test_checkout_sold_out_during_reservation(buyer, store, product, monkeypatch):
    from apps.orders import services as orders_services

    def sold_out(**kwargs):
        raise OutOfStock(
            [{"sku": product.sku, "name": product.name, "requested": 1, "available": 0}]
        )

    buyer.taps(shop_id("add", product.pk, 1))
    monkeypatch.setattr(orders_services, "start_checkout", sold_out)

    assert buyer.taps(shop_id("checkout")) is True

    assert body_of(buyer.last_reply()) == content.SOLD_OUT
    assert button_ids(buyer.last_reply()) == [shop_id("cart"), shop_id("browse")]


def test_my_orders_and_talk_to_us(buyer, store, conversation, orders_calls):
    buyer.taps(shop_id("orders"))
    assert [c.pk for c in orders_calls.recent_orders] == [conversation.pk]
    assert buyer.replies() == []

    buyer.taps(shop_id("talk"))
    [support] = buyer.replies()
    assert support.type == Message.Type.TEXT
    assert support.text == "Call us on 98000 00000 between 10 and 7."


def test_talk_to_us_default_message(buyer, store):
    store.support_message = ""
    store.save()

    buyer.taps(shop_id("talk"))

    assert buyer.last_reply().text == content.DEFAULT_SUPPORT


# --- Orders scopes ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply_id",
    [
        "upc:chk:pay:0b7f6f7e-4a57-4b3e-9a4a-4b0d1f3f7c11:cod",
        "upc:ord:list",
        "upc:nfm:address_message",
    ],
)
def test_checkout_replies_are_forwarded(buyer, store, orders_calls, reply_id):
    assert buyer.taps(reply_id) is True

    [(message, reply)] = orders_calls.replies
    assert message.pk == buyer.last.pk
    assert isinstance(reply, ReplyId)
    assert str(reply) == reply_id
    assert buyer.replies() == []


def test_unhandled_checkout_reply_gets_the_menu(buyer, store, orders_calls):
    orders_calls.reply_result = False

    buyer.taps("upc:chk:retry:0b7f6f7e-4a57-4b3e-9a4a-4b0d1f3f7c11")

    assert_unavailable_menu(buyer.last_reply())


def test_reply_id_is_read_from_the_payload(buyer, store, conversation, orders_calls):
    message = MessageFactory(
        conversation=conversation,
        inbound=True,
        type=Message.Type.INTERACTIVE,
        text="Address shared",
        payload={"interactive": {"type": "nfm_reply", "nfm_reply": {"name": "address_message"}}},
    )

    assert services.handle_inbound(message.pk) is True

    [(_, reply)] = orders_calls.replies
    assert (reply.scope, reply.action) == ("nfm", "address_message")


def test_seller_alert_replies_are_ignored(buyer, store):
    assert buyer.taps("upc:alerts:orders") is False
    assert buyer.replies() == []


# --- Stale and invalid ids ----------------------------------------------------------------------


def test_deleted_product(buyer, store, product):
    product_id = product.pk
    product.delete()

    assert buyer.taps(shop_id("prod", product_id)) is True

    assert_unavailable_menu(buyer.last_reply())


def test_product_of_another_workspace(buyer, store, other_workspace):
    foreign = ProductFactory(workspace=other_workspace)

    buyer.taps(shop_id("add", foreign.pk, 1))

    assert_unavailable_menu(buyer.last_reply())
    assert session_of(buyer.last.conversation).cart == []


@pytest.mark.parametrize(
    "make_id",
    [
        lambda sweets, product: shop_id("col", sweets.pk, 90),  # stale offset
        lambda sweets, product: shop_id("col", "0b7f6f7e-4a57-4b3e-9a4a-4b0d1f3f7c11", 0),
        lambda sweets, product: shop_id("col", "nonsense", 0),
        lambda sweets, product: shop_id("add", product.pk, "lots"),
        lambda sweets, product: shop_id("add", product.pk, 0),
        lambda sweets, product: shop_id("prod"),  # missing argument
        lambda sweets, product: shop_id("dance"),  # unknown action
    ],
)
def test_invalid_ids(buyer, store, sweets, product, make_id):
    buyer.taps(make_id(sweets, product))

    [reply] = buyer.replies()
    assert_unavailable_menu(reply)


def test_inactive_collection(buyer, store, sweets, product):
    sweets.is_active = False
    sweets.save()

    buyer.taps(shop_id("col", sweets.pk, 0))

    assert_unavailable_menu(buyer.last_reply())


def test_typed_quantity_for_a_product_that_went_out_of_stock(buyer, store, product, conversation):
    buyer.taps(shop_id("qty", product.pk))
    product.stock_qty = 0
    product.save()

    buyer.says("2")

    assert_unavailable_menu(buyer.last_reply())
    session = session_of(conversation)
    assert (session.state, session.cart) == (BotSession.State.IDLE, [])


# --- Idempotency, sessions and gating -----------------------------------------------------------


def test_same_message_is_handled_once(buyer, store, product, conversation):
    buyer.taps(shop_id("add", product.pk, 2))
    replies = len(buyer.replies())

    assert services.handle_inbound(buyer.last.pk, reply_id=shop_id("add", product.pk, 2)) is False

    assert len(buyer.replies()) == replies
    assert session_of(conversation).cart == [{"product_id": str(product.pk), "quantity": 2}]


def test_expired_session_is_reset(buyer, store, product, conversation, orders_calls):
    long_ago = timezone.now() - timedelta(hours=25)
    BotSessionFactory(
        conversation=conversation,
        state=BotSession.State.AWAITING_QUANTITY,
        cart=[{"product_id": str(product.pk), "quantity": 3}],
        context={"product_id": str(product.pk)},
        last_message_at=long_ago,
    )

    assert buyer.says("2") is False  # not a quantity any more

    assert orders_calls.texts == [buyer.last]
    session = session_of(conversation)
    assert (session.state, session.cart) == (BotSession.State.IDLE, [])
    assert session.last_message_at == buyer.last.sent_at
    assert session.expires_at == buyer.last.sent_at + timedelta(hours=24)
    assert buyer.replies() == []


def test_active_session_keeps_its_cart(buyer, store, product, conversation):
    BotSessionFactory(
        conversation=conversation,
        cart=[{"product_id": str(product.pk), "quantity": 3}],
        last_message_at=timezone.now() - timedelta(hours=23),
    )

    buyer.taps(shop_id("cart"))

    assert "3 x Kaju Katli 500g" in body_of(buyer.last_reply())


def test_disabled_store_does_nothing(buyer, store, product, orders_calls):
    store.enabled = False
    store.save()

    assert buyer.says("hi") is False
    assert buyer.taps(shop_id("add", product.pk, 1)) is False

    assert buyer.replies() == []
    assert not BotSession.objects.exists()
    assert orders_calls.texts == []


def test_store_without_the_commerce_feature_does_nothing(buyer, store, workspace, orders_calls):
    subscription = billing_services.get_subscription(workspace)
    subscription.status = "expired"
    subscription.save()

    assert buyer.says("hi") is False
    assert buyer.sends_order([{"product_retailer_id": "SKU", "quantity": 1}]) is False

    assert buyer.replies() == []
    assert orders_calls.start_checkout == []


def test_other_numbers_of_the_workspace_are_not_the_store(store, workspace, contact, orders_calls):
    other_number = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)
    conversation = ConversationFactory(
        workspace=workspace, contact=contact, phone_number=other_number, window_open=True
    )
    message = MessageFactory(conversation=conversation, inbound=True, text="hi")

    assert services.handle_inbound(message.pk) is False
    assert not Message.objects.filter(direction=Message.Direction.OUTBOUND).exists()


def test_chosen_store_number(store, workspace, contact, orders_calls):
    chosen = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)
    store.phone_number = chosen
    store.save()
    conversation = ConversationFactory(
        workspace=workspace, contact=contact, phone_number=chosen, window_open=True
    )
    message = MessageFactory(conversation=conversation, inbound=True, text="menu")

    assert services.handle_inbound(message.pk) is True


def test_outside_the_service_window_the_bot_stops_quietly(buyer, store, conversation):
    conversation.service_window_expires_at = timezone.now() - timedelta(hours=1)
    conversation.save()

    assert buyer.says("hi") is True

    assert buyer.replies() == []
    assert session_of(conversation).context["handled"] == [buyer.last.wamid]


def test_outbound_messages_are_ignored(store, conversation):
    message = MessageFactory(conversation=conversation, text="hi")

    assert services.handle_inbound(message.pk) is False
