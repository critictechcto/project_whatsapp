"""The bot buyer journey end to end: shop, check out, pay online, get alerts, ship from WhatsApp."""

import pytest
from django.urls import reverse

from apps.message_templates.factories import MessageTemplateFactory, standard_components
from apps.message_templates.models import MessageTemplate
from apps.orders.models import Order, OrderEvent
from apps.payments.models import PaymentLink

from .test_e2e_commerce_support import (
    SELLER_PHONE,
    body_text,
    close_buyer_window,
    last_buyer_message,
    only_link,
    option_id,
    platform_sends,
    reply_ids,
    shop_to_checkout,
    store_sends,
)

pytest_plugins = ["tests.test_e2e_commerce_support"]
pytestmark = pytest.mark.django_db
SELLER_WA_ID = SELLER_PHONE.removeprefix("+")


def _open_return_page(client, on_commit, link: PaymentLink):
    with on_commit():
        return client.get(reverse("payments_return:link-return", args=[link.pk]))


def _pay_and_confirm(workspace, buyer, fake_graph, fake_payments, client, on_commit, kaju):
    order = shop_to_checkout(buyer, workspace)
    assert order.status == Order.Status.AWAITING_ADDRESS
    assert order.source == Order.Source.BOT
    assert order.total_paise == 24900

    buyer.shares_address()
    order.refresh_from_db()
    assert order.status == Order.Status.AWAITING_PAYMENT_METHOD
    assert order.address["city"] == "New Delhi"
    assert order.address["pincode"] == "110001"

    buyer.taps(option_id(last_buyer_message(workspace), "Pay online"), "Pay online")
    order.refresh_from_db()
    kaju.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT
    assert kaju.stock_qty == 9
    link = only_link(order)
    assert link.status == PaymentLink.Status.CREATED
    assert link.amount_paise == 24900
    cta = store_sends(fake_graph)[-1]
    assert cta["type"] == "interactive"
    assert cta["interactive"]["type"] == "cta_url"
    assert cta["interactive"]["action"]["parameters"]["url"] == link.short_url

    fake_payments.mark_paid(link.provider_link_id)
    response = _open_return_page(client, on_commit, link)
    assert response.status_code == 200
    assert "received" in response.content.decode().lower()

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert order.payment_status == Order.PaymentStatus.PAID
    return order


def test_bot_journey_pays_online_and_the_seller_ships_from_whatsapp(
    workspace,
    buyer,
    seller,
    kaju,
    gateway,
    recipient,
    fake_graph,
    fake_payments,
    client,
    frames,
    on_commit,
):
    order = _pay_and_confirm(workspace, buyer, fake_graph, fake_payments, client, on_commit, kaju)

    confirmation = last_buyer_message(workspace)
    assert order.number in body_text(confirmation)
    assert option_id(confirmation, "View order").startswith("upc:ord:view:")
    assert OrderEvent.objects.filter(
        order=order, type=OrderEvent.Type.NOTIFICATION_SENT, metadata__notification="confirmed"
    ).exists()

    # The verified seller gets the new-order alert from the UpChatz number.
    [alert] = platform_sends(fake_graph, SELLER_WA_ID)
    assert order.number in str(alert)
    ship_id = next(i for i in reply_ids(alert) if i.startswith("upc:alerts:ship:"))
    assert ship_id == f"upc:alerts:ship:{order.pk}"

    seller.taps(ship_id, "Mark shipped")
    prompt = platform_sends(fake_graph, SELLER_WA_ID)[-1]
    assert "AWB" in str(prompt)

    seller.says("Delhivery 1234567890 https://track.example/1")
    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPED
    assert (order.courier_name, order.awb_number, order.tracking_url) == (
        "Delhivery",
        "1234567890",
        "https://track.example/1",
    )
    assert "marked as shipped" in str(platform_sends(fake_graph, SELLER_WA_ID)[-1])

    shipped = store_sends(fake_graph)[-1]
    assert shipped["to"] == order.contact.wa_id
    assert shipped["interactive"]["type"] == "cta_url"
    assert shipped["interactive"]["action"]["parameters"]["url"] == "https://track.example/1"

    updates = [f for f in frames if f["type"] == "order.updated"]
    assert updates[-1]["data"]["status"] == Order.Status.SHIPPED


def test_shipped_update_uses_the_mapped_template_outside_the_window(
    workspace,
    e2e_number,
    store,
    buyer,
    seller,
    kaju,
    gateway,
    recipient,
    fake_graph,
    fake_payments,
    client,
    on_commit,
):
    template = MessageTemplateFactory(
        waba=e2e_number.waba,
        name="upc_order_shipped",
        status=MessageTemplate.Status.APPROVED,
        components=standard_components(
            "Hi {{1}}, order {{2}} has shipped with {{3}} (AWB {{4}}). Track: {{5}}"
        ),
    )
    store.shipped_template = template
    store.save(update_fields=["shipped_template"])
    order = _pay_and_confirm(workspace, buyer, fake_graph, fake_payments, client, on_commit, kaju)

    close_buyer_window(workspace)
    [alert] = platform_sends(fake_graph, SELLER_WA_ID)
    seller.taps(f"upc:alerts:ship:{order.pk}", "Mark shipped")
    seller.says("Delhivery 1234567890 https://track.example/1")

    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPED
    sent = store_sends(fake_graph)[-1]
    assert sent["type"] == "template"
    assert sent["template"]["name"] == "upc_order_shipped"
    params = [p["text"] for p in sent["template"]["components"][0]["parameters"]]
    assert params == [
        "Priya Sharma",
        order.number,
        "Delhivery",
        "1234567890",
        "https://track.example/1",
    ]
    assert OrderEvent.objects.filter(
        order=order, type=OrderEvent.Type.NOTIFICATION_SENT, metadata__notification="shipped"
    ).exists()
    assert alert  # the new-order alert still went out
