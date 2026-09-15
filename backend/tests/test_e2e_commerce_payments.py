"""Online payments end to end: checkout expiry, payment after the checkout closed, polling and
duplicate deliveries of Meta webhooks, gateway webhooks and the buyer return page."""

from datetime import timedelta

import pytest
from django.urls import reverse

from apps.catalog.models import Product
from apps.orders.models import Order, OrderEvent
from apps.orders.tasks import expire_checkouts
from apps.payments.exceptions import PaymentProviderError
from apps.payments.models import PaymentLink, PaymentWebhookEvent
from apps.payments.tasks import poll_open_links

from .test_e2e_commerce_support import (
    SELLER_PHONE,
    body_text,
    buyer_messages,
    last_buyer_message,
    only_link,
    pay_online,
    platform_sends,
)

pytest_plugins = ["tests.test_e2e_commerce_support"]
pytestmark = pytest.mark.django_db
SELLER_WA_ID = SELLER_PHONE.removeprefix("+")


def _confirmations(order) -> int:
    return OrderEvent.objects.filter(
        order=order, type=OrderEvent.Type.NOTIFICATION_SENT, metadata__notification="confirmed"
    ).count()


def _return_page(client, on_commit, link):
    with on_commit():
        return client.get(reverse("payments_return:link-return", args=[link.pk]))


def test_expiry_cancels_the_link_before_releasing_stock(
    workspace, buyer, kaju, gateway, fake_payments, on_commit, time_machine
):
    order = pay_online(buyer, workspace)
    link = only_link(order)

    # A retryable gateway error keeps the order (and its stock) for the next run.
    time_machine.move_to(order.expires_at + timedelta(minutes=1))
    fake_payments.fail_next("cancel_link")
    with on_commit():
        assert expire_checkouts.delay().get() == 0
    order.refresh_from_db()
    kaju.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT
    assert kaju.stock_qty == 9

    with on_commit():
        assert expire_checkouts.delay().get() == 1

    order.refresh_from_db()
    link.refresh_from_db()
    kaju.refresh_from_db()
    assert fake_payments.calls_to("cancel_link") == [link.provider_link_id] * 2
    assert link.status == PaymentLink.Status.CANCELLED
    assert order.status == Order.Status.EXPIRED
    assert kaju.stock_qty == 10
    assert f"Your checkout for order {order.number} has expired." in body_text(
        last_buyer_message(workspace)
    )


def test_payment_after_the_stock_was_released_needs_attention(
    workspace,
    buyer,
    kaju,
    gateway,
    recipient,
    fake_payments,
    fake_graph,
    client,
    on_commit,
    time_machine,
):
    order = pay_online(buyer, workspace)
    link = only_link(order)
    fake_payments.fail_next(
        "cancel_link",
        PaymentProviderError("Link not found.", provider="fake", status_code=400, retryable=False),
    )
    time_machine.move_to(order.expires_at + timedelta(minutes=1))
    with on_commit():
        expire_checkouts.delay()
    order.refresh_from_db()
    assert order.status == Order.Status.EXPIRED
    # Someone else buys the last pieces before the buyer finishes paying.
    Product.objects.filter(pk=kaju.pk).update(stock_qty=0)

    fake_payments.mark_paid(link.provider_link_id)
    assert _return_page(client, on_commit, link).status_code == 200

    order.refresh_from_db()
    kaju.refresh_from_db()
    assert order.status == Order.Status.NEEDS_ATTENTION
    assert order.payment_status == Order.PaymentStatus.PAID
    assert kaju.stock_qty == 0
    [alert] = platform_sends(fake_graph, SELLER_WA_ID)
    assert order.number in str(alert)
    assert "attention" in str(alert).lower()


def test_polling_alone_confirms_a_paid_link(
    workspace, buyer, kaju, gateway, recipient, fake_payments, fake_graph, on_commit, time_machine
):
    order = pay_online(buyer, workspace)
    link = only_link(order)
    fake_payments.mark_paid(link.provider_link_id)

    time_machine.move_to(link.created_at + timedelta(minutes=1))
    with on_commit():
        poll_open_links.delay()
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT  # not due yet

    time_machine.move_to(link.created_at + timedelta(minutes=3))
    with on_commit():
        poll_open_links.delay()

    order.refresh_from_db()
    link.refresh_from_db()
    assert link.status == PaymentLink.Status.PAID
    assert order.status == Order.Status.CONFIRMED
    assert order.payment_status == Order.PaymentStatus.PAID
    assert _confirmations(order) == 1
    assert len(platform_sends(fake_graph, SELLER_WA_ID)) == 1


def test_a_redelivered_meta_webhook_is_handled_once(workspace, buyer, kaju, fake_graph):
    payload = buyer.says("hi")
    sent = len(fake_graph.sent_messages)
    messages = len(buyer_messages(workspace))
    assert messages == 1

    buyer.deliver(payload)

    assert len(fake_graph.sent_messages) == sent
    assert len(buyer_messages(workspace)) == messages


def test_a_duplicate_gateway_webhook_confirms_once(
    workspace, buyer, kaju, gateway, recipient, fake_payments, fake_graph, client, on_commit
):
    order = pay_online(buyer, workspace)
    link = only_link(order)
    fake_payments.mark_paid(link.provider_link_id)
    headers, body = fake_payments.webhook(link.provider_link_id, event_id="evt_e2e_1")
    url = reverse("payments_webhooks:merchant-webhook", args=[gateway.webhook_token])

    for _ in range(2):
        with on_commit():
            response = client.post(url, body, content_type="application/json", headers=headers)
        assert response.status_code == 200, response.content

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert PaymentWebhookEvent.objects.filter(event_id="evt_e2e_1").count() == 1
    assert order.events.filter(type=OrderEvent.Type.PAYMENT_RECEIVED).count() == 1
    assert _confirmations(order) == 1
    assert len(platform_sends(fake_graph, SELLER_WA_ID)) == 1


def test_opening_the_return_page_twice_confirms_once(
    workspace, buyer, kaju, gateway, recipient, fake_payments, fake_graph, client, on_commit
):
    order = pay_online(buyer, workspace)
    link = only_link(order)
    fake_payments.mark_paid(link.provider_link_id)

    for _ in range(2):
        response = _return_page(client, on_commit, link)
        assert response.status_code == 200
        assert "received" in response.content.decode().lower()

    order.refresh_from_db()
    kaju.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert kaju.stock_qty == 9
    assert order.events.filter(type=OrderEvent.Type.PAYMENT_RECEIVED).count() == 1
    assert _confirmations(order) == 1
    assert len(platform_sends(fake_graph, SELLER_WA_ID)) == 1
