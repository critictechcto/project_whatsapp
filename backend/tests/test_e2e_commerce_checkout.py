"""Checkout end to end: native carts, cash on delivery, superseded and rejected checkouts, stale
buttons and seller commands from an unverified alert number."""

import json

import pytest

from apps.catalog.models import Product
from apps.orders.models import Order
from apps.payments.models import PaymentLink
from apps.seller_alerts.factories import AlertRecipientFactory
from apps.seller_alerts.models import AlertRecipient, PendingSellerReply
from common.roles import Role

from .test_e2e_commerce_support import (
    SELLER_PHONE,
    body_text,
    buyer_messages,
    checkout_to_payment_choice,
    current_order,
    last_buyer_message,
    only_link,
    option_id,
    pay_online,
    platform_sends,
    shop_to_checkout,
    tap_checkout,
)

pytest_plugins = ["tests.test_e2e_commerce_support"]
pytestmark = pytest.mark.django_db
SELLER_WA_ID = SELLER_PHONE.removeprefix("+")
STALE_TEXT = "This option is no longer available."


@pytest.fixture
def cod_store(store):
    store.cod_enabled = True
    store.save(update_fields=["cod_enabled"])
    return store


def test_native_cart_with_a_changed_price_asks_for_confirmation_then_the_address(
    workspace, buyer, kaju
):
    buyer.sends_cart(
        [
            {
                "product_retailer_id": kaju.sku,
                "quantity": 2,
                "item_price": 199,
                "currency": "INR",
            }
        ]
    )

    order = current_order(workspace)
    assert order.source == Order.Source.NATIVE_CART
    assert order.status == Order.Status.AWAITING_CONFIRMATION
    assert order.total_paise == 2 * 24900
    prompt = last_buyer_message(workspace)
    assert "₹498" in body_text(prompt)

    buyer.taps(option_id(prompt, "Confirm"), "Confirm")

    order.refresh_from_db()
    assert order.status == Order.Status.AWAITING_ADDRESS
    ask = last_buyer_message(workspace)
    assert ask.payload["type"] == "interactive"
    assert ask.payload["interactive"]["type"] == "address_message"


def test_cash_on_delivery_through_to_collection_from_the_dashboard(
    workspace, cod_store, buyer, kaju, auth_client
):
    order = checkout_to_payment_choice(buyer, workspace)
    offer = last_buyer_message(workspace)
    with pytest.raises(AssertionError):
        option_id(offer, "Pay online")  # no gateway connected

    buyer.taps(option_id(offer, "Cash on delivery"), "Cash on delivery")

    order.refresh_from_db()
    kaju.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert order.payment_status == Order.PaymentStatus.COD_PENDING
    assert order.payment_method == Order.PaymentMethod.COD
    assert kaju.stock_qty == 9
    assert not PaymentLink.objects.exists()
    assert order.number in body_text(last_buyer_message(workspace))

    client = auth_client(Role.AGENT)
    base = f"/api/v1/orders/{order.pk}/"
    for body in (
        {"to_status": "packed"},
        {"to_status": "shipped", "courier_name": "Delhivery", "awb_number": "1234567890"},
        {"to_status": "delivered"},
    ):
        response = client.post(f"{base}transition/", body, format="json")
        assert response.status_code == 200, response.content
        assert response.json()["status"] == body["to_status"]

    response = client.post(f"{base}mark-cod-collected/", format="json")
    assert response.status_code == 200, response.content
    order.refresh_from_db()
    assert order.status == Order.Status.DELIVERED
    assert order.payment_status == Order.PaymentStatus.COD_COLLECTED
    assert order.cod_collected_at is not None


def test_a_second_cart_supersedes_the_active_checkout(
    workspace, buyer, kaju, gateway, recipient, fake_payments, fake_graph
):
    first = pay_online(buyer, workspace)
    link = only_link(first)
    kaju.refresh_from_db()
    assert kaju.stock_qty == 9

    second = shop_to_checkout(buyer, workspace)

    assert second.pk != first.pk
    first.refresh_from_db()
    link.refresh_from_db()
    kaju.refresh_from_db()
    assert first.status == Order.Status.CANCELLED
    assert link.status == PaymentLink.Status.CANCELLED
    assert fake_payments.links[link.provider_link_id].status == "cancelled"
    assert fake_payments.calls_to("cancel_link") == [link.provider_link_id]
    assert kaju.stock_qty == 10
    assert second.status == Order.Status.AWAITING_ADDRESS
    texts = [body_text(m) for m in buyer_messages(workspace)]
    assert f"Your earlier checkout {first.number} was replaced by this new one." in texts


@pytest.mark.xfail(
    strict=True,
    reason=(
        "seller_alerts.services.alert_event_for alerts order_cancelled for any buyer/system "
        "cancellation, including checkouts the seller never got a new-order alert for "
        "(superseded carts, Edit cart, Cancel order during checkout)."
    ),
)
def test_a_superseded_checkout_does_not_alert_the_seller(
    workspace, buyer, kaju, gateway, recipient, fake_payments, fake_graph
):
    pay_online(buyer, workspace)
    shop_to_checkout(buyer, workspace)

    sent = platform_sends(fake_graph, SELLER_WA_ID)
    assert sent == [], json.dumps(sent, ensure_ascii=False)


def test_items_that_run_out_before_the_payment_choice_are_not_reserved(
    workspace, buyer, kaju, gateway, fake_payments
):
    order = checkout_to_payment_choice(buyer, workspace)
    offer = last_buyer_message(workspace)
    Product.objects.filter(pk=kaju.pk).update(stock_qty=0)

    buyer.taps(option_id(offer, "Pay online"), "Pay online")

    order.refresh_from_db()
    kaju.refresh_from_db()
    assert "Sorry, some items just ran out:" in body_text(last_buyer_message(workspace))
    assert kaju.stock_qty == 0
    assert order.status != Order.Status.PENDING_PAYMENT
    assert not PaymentLink.objects.exists()
    assert fake_payments.calls_to("create_link") == []


def test_an_old_checkout_button_is_refused_after_the_order_moved_on(
    workspace, cod_store, buyer, kaju
):
    order = checkout_to_payment_choice(buyer, workspace)
    offer = last_buyer_message(workspace)
    cod_id = option_id(offer, "Cash on delivery")
    cancel_id = option_id(offer, "Cancel order")
    buyer.taps(cod_id, "Cash on delivery")
    order.refresh_from_db()
    before = (order.status, order.payment_status, order.updated_at)
    messages = len(buyer_messages(workspace))

    for reply_id, title in ((cod_id, "Cash on delivery"), (cancel_id, "Cancel order")):
        buyer.taps(reply_id, title)
        assert body_text(last_buyer_message(workspace)) == STALE_TEXT

    order.refresh_from_db()
    kaju.refresh_from_db()
    assert (order.status, order.payment_status, order.updated_at) == before
    assert kaju.stock_qty == 9
    assert len(buyer_messages(workspace)) == messages + 2


def test_commands_from_an_unverified_alert_number_are_ignored(
    workspace, cod_store, buyer, seller, kaju, fake_graph
):
    AlertRecipientFactory(
        workspace=workspace,
        phone_e164=SELLER_PHONE,
        status=AlertRecipient.Status.PENDING,
        verified_at=None,
    )
    order = checkout_to_payment_choice(buyer, workspace)
    buyer.taps(option_id(last_buyer_message(workspace), "Cash on delivery"), "Cash on delivery")
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert platform_sends(fake_graph, SELLER_WA_ID) == []  # no alerts before verification

    seller.taps(f"upc:alerts:pack:{order.pk}", "Mark packed")
    seller.taps(f"upc:alerts:ship:{order.pk}", "Mark shipped")
    seller.says("Delhivery 1234567890")
    seller.says("ORDERS")

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert not PendingSellerReply.objects.exists()
    assert platform_sends(fake_graph, SELLER_WA_ID) == []


def test_a_cart_below_the_minimum_order_creates_no_order(workspace, store, buyer, kaju):
    store.min_order_paise = 50000
    store.save(update_fields=["min_order_paise"])

    tap_checkout(buyer, workspace)

    assert not Order.objects.exists()
    assert body_text(last_buyer_message(workspace)).startswith("The minimum order is ₹500")
    kaju.refresh_from_db()
    assert kaju.stock_qty == 10
