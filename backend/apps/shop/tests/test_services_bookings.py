"""Services in the bot: kind-separated carts, the Book card, offer codes and reminder buttons."""

import pytest

from apps.catalog.factories import ProductFactory
from apps.inbox.factories import MessageFactory
from apps.inbox.models import Message
from apps.offers import services as offers
from apps.shop import content, services
from apps.shop.content import shop_id
from apps.shop.models import BotSession
from common.commerce import build_reply_id

from .helpers import body_of, button_ids, button_titles

pytestmark = pytest.mark.django_db


@pytest.fixture
def haircut(workspace, sweets):
    return ProductFactory(
        workspace=workspace,
        collection=sweets,
        service=True,
        name="Haircut",
        price_paise=49900,
        duration_minutes=45,
    )


def cart_ids(conversation) -> list[str]:
    session = BotSession.objects.get(conversation=conversation)
    return [line["product_id"] for line in session.cart]


def test_service_card_shows_the_duration_and_a_book_button(haircut):
    card = content.product_card(haircut, back_id=shop_id("menu"))

    body = card.interactive["body"]["text"]
    assert "45 min" in body
    buttons = [button["reply"]["title"] for button in card.interactive["action"]["buttons"]]
    assert buttons[0] == "Book"


def test_product_card_keeps_add_to_cart(product):
    card = content.product_card(product, back_id=shop_id("menu"))

    assert card.interactive["action"]["buttons"][0]["reply"]["title"] == "Add to cart"
    assert "min" not in card.interactive["body"]["text"]


@pytest.mark.parametrize("minutes,text", [(45, "45 min"), (60, "1 hr"), (90, "1 hr 30 min")])
def test_duration_text(haircut, minutes, text):
    haircut.duration_minutes = minutes
    assert content.duration_text(haircut) == text


def test_adding_a_service_to_a_cart_of_products_adds_nothing(
    buyer, store, product, haircut, conversation
):
    buyer.taps(shop_id("add", product.pk, 1))
    before = cart_ids(conversation)

    buyer.taps(shop_id("add", haircut.pk, 1))

    assert cart_ids(conversation) == before == [str(product.pk)]
    reply = buyer.last_reply()
    assert "Services are booked separately" in body_of(reply)
    assert button_ids(reply) == [shop_id("checkout"), shop_id("clear")]
    assert button_titles(reply) == ["Checkout", "Clear cart"]


def test_adding_a_product_to_a_booking_cart_adds_nothing(
    buyer, store, product, haircut, conversation
):
    buyer.taps(shop_id("add", haircut.pk, 1))

    buyer.taps(shop_id("add", product.pk, 1))

    assert cart_ids(conversation) == [str(haircut.pk)]
    assert "Products are ordered separately" in body_of(buyer.last_reply())


def test_services_can_share_a_cart(buyer, store, haircut, workspace, sweets, conversation):
    other = ProductFactory(workspace=workspace, collection=sweets, service=True, name="Shave")

    buyer.taps(shop_id("add", haircut.pk, 1))
    buyer.taps(shop_id("add", other.pk, 1))

    assert set(cart_ids(conversation)) == {str(haircut.pk), str(other.pk)}


def test_an_offer_code_is_never_a_quantity(
    buyer, store, product, conversation, orders_calls, monkeypatch
):
    monkeypatch.setattr(offers, "match_code", lambda workspace_id, text: object())
    handled = buyer.says("10")

    assert handled is False
    assert orders_calls.texts == []
    assert buyer.replies() == []


def test_a_template_quick_reply_reaches_orders(buyer, store, conversation, orders_calls):
    reply_id = build_reply_id("ord", "attend", "8f8b9f7e-3c1d-4f43-9a55-6d6c3d1b2a10")
    message = MessageFactory(
        conversation=conversation,
        inbound=True,
        type=Message.Type.BUTTON,
        text="I'll be there",
        payload={"type": "button", "button": {"payload": reply_id, "text": "I'll be there"}},
    )

    assert services.handle_inbound(message.pk) is True

    [(_, reply)] = orders_calls.replies
    assert (reply.scope, reply.action) == ("ord", "attend")
