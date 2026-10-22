"""Payment links: the link task, payment events and checkout expiry."""

from datetime import timedelta

import pytest
from celery.exceptions import Retry
from django.utils import timezone

from apps.catalog.factories import ProductFactory
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.orders import checkout, notifications
from apps.orders.factories import OrderEventFactory
from apps.orders.models import Order, StoreSettings
from apps.orders.tasks import (
    PAYMENT_LINK_MAX_RETRIES,
    expire_checkouts,
    send_payment_link,
    send_payment_reminders,
)
from apps.payments import services as payment_services
from apps.payments.exceptions import PaymentAccountInvalid, PaymentProviderError
from apps.payments.factories import PaymentLinkFactory
from apps.payments.models import PaymentLink
from common import events
from common.commerce import build_reply_id

from .helpers import (
    cancelled_event,
    content_text,
    event_types,
    expired_event,
    last_outbound,
    paid_event,
    pending_order,
    press,
    refresh,
    reply_ids,
    start,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def tracked(workspace):
    return ProductFactory(workspace=workspace, price_paise=24900, stock_qty=5)


def stock(product) -> int:
    product.refresh_from_db()
    return product.stock_qty


# --- Payment events -----------------------------------------------------------------------------


def test_paid_link_confirms_a_pending_order_once(conversation, tracked):
    order = pending_order(conversation, tracked, quantity=2)
    link = PaymentLinkFactory(order=order)

    events.emit(events.payment_link_paid, paid_event(link))
    events.emit(events.payment_link_paid, paid_event(link))

    order = refresh(order)
    assert order.status == Order.Status.CONFIRMED
    assert order.payment_status == Order.PaymentStatus.PAID
    assert order.paid_at is not None
    types = event_types(order)
    assert types.count("payment_received") == 1
    assert types.count("status_changed") == 1
    assert "notification_sent" in types


def test_payment_after_expiry_revives_the_order_when_stock_is_left(conversation, tracked):
    order = pending_order(
        conversation, tracked, quantity=2, status=Order.Status.EXPIRED, stock_reserved=False
    )
    link = PaymentLinkFactory(order=order, status="expired")

    events.emit(events.payment_link_paid, paid_event(link))

    order = refresh(order)
    assert (order.status, order.payment_status) == (Order.Status.CONFIRMED, "paid")
    assert order.stock_reserved
    assert stock(tracked) == 3


def test_payment_after_expiry_needs_attention_without_stock(conversation, tracked):
    tracked.stock_qty = 1
    tracked.save()
    order = pending_order(
        conversation, tracked, quantity=2, status=Order.Status.EXPIRED, stock_reserved=False
    )
    link = PaymentLinkFactory(order=order, status="expired")

    events.emit(events.payment_link_paid, paid_event(link))

    order = refresh(order)
    assert (order.status, order.payment_status) == (Order.Status.NEEDS_ATTENTION, "paid")
    assert not order.stock_reserved
    assert stock(tracked) == 1
    assert "received your payment" in last_outbound(conversation.contact).text


def test_paid_checkout_out_of_stock_needs_attention(conversation, tracked):
    tracked.stock_qty = 0
    tracked.save()
    order = pending_order(
        conversation,
        tracked,
        quantity=2,
        status=Order.Status.AWAITING_PAYMENT_METHOD,
        stock_reserved=False,
    )
    link = PaymentLinkFactory(order=order, status="expired")

    events.emit(events.payment_link_paid, paid_event(link))

    assert refresh(order).status == Order.Status.NEEDS_ATTENTION


def test_payment_for_an_order_the_seller_cancelled_needs_attention(conversation, tracked):
    order = pending_order(
        conversation, tracked, quantity=2, status=Order.Status.CANCELLED, stock_reserved=False
    )
    OrderEventFactory(order=order, type="status_changed", to_status="cancelled", actor="dashboard")
    link = PaymentLinkFactory(order=order, status="cancelled")

    events.emit(events.payment_link_paid, paid_event(link))

    assert refresh(order).status == Order.Status.NEEDS_ATTENTION
    assert stock(tracked) == 5


def test_expired_link_releases_stock_and_offers_another_try(conversation, store, tracked, online):
    store.cod_enabled = True
    store.save()
    tracked.stock_qty = 3
    tracked.save()
    order = pending_order(conversation, tracked, quantity=2)
    link = PaymentLinkFactory(order=order, status="expired")

    events.emit(events.payment_link_expired, expired_event(link))

    order = refresh(order)
    assert order.status == Order.Status.AWAITING_PAYMENT_METHOD
    assert not order.stock_reserved
    assert stock(tracked) == 5
    assert "payment_link_expired" in event_types(order)
    ids = reply_ids(last_outbound(conversation.contact))
    assert build_reply_id("chk", "retry", order.pk) in ids
    assert build_reply_id("chk", "pay", order.pk, "cod") in ids


def test_closed_event_for_an_older_link_is_ignored(conversation, tracked):
    order = pending_order(conversation, tracked, quantity=1)
    old = PaymentLinkFactory(order=order, status="cancelled")
    PaymentLinkFactory(order=order)
    type(old).objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(minutes=5))

    events.emit(events.payment_link_cancelled, cancelled_event(old))

    assert refresh(order).status == Order.Status.PENDING_PAYMENT


def test_try_again_creates_a_new_link_attempt(
    conversation, tracked, online, payment_links, django_capture_on_commit_callbacks
):
    order = pending_order(
        conversation,
        tracked,
        quantity=1,
        status=Order.Status.AWAITING_PAYMENT_METHOD,
        stock_reserved=False,
        checkout_attempt=1,
    )

    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, build_reply_id("chk", "retry", order.pk))

    order = refresh(order)
    assert (order.status, order.checkout_attempt) == (Order.Status.PENDING_PAYMENT, 2)
    assert [call["reference_id"] for call in payment_links] == [f"{order.number}-2"]
    assert stock(tracked) == 4


# --- Link task ----------------------------------------------------------------------------------


def test_link_task_account_error_offers_cash_on_delivery(conversation, store, tracked, monkeypatch):
    store.cod_enabled = True
    store.save()
    tracked.stock_qty = 3
    tracked.save()
    order = pending_order(conversation, tracked, quantity=2)

    def create_payment_link(**kwargs):
        raise PaymentAccountInvalid()

    monkeypatch.setattr(payment_services, "create_payment_link", create_payment_link)

    send_payment_link.apply(args=[str(order.pk), 1])

    order = refresh(order)
    assert order.status == Order.Status.AWAITING_PAYMENT_METHOD
    assert not order.stock_reserved
    assert stock(tracked) == 5
    message = last_outbound(conversation.contact)
    assert reply_ids(message) == [
        build_reply_id("chk", "pay", order.pk, "cod"),
        build_reply_id("chk", "cancel", order.pk),
    ]
    assert "online payment isn't available" in content_text(message)


def test_link_task_retries_retryable_errors_then_offers_a_retry(
    conversation, tracked, online, monkeypatch
):
    order = pending_order(conversation, tracked, quantity=1)
    calls = []

    def create_payment_link(**kwargs):
        calls.append(kwargs)
        raise PaymentProviderError("Gateway timeout", provider="razorpay", retryable=True)

    monkeypatch.setattr(payment_services, "create_payment_link", create_payment_link)

    with pytest.raises(Retry):
        send_payment_link.apply(args=[str(order.pk), 1])
    assert refresh(order).status == Order.Status.PENDING_PAYMENT
    calls.clear()

    send_payment_link.apply(args=[str(order.pk), 1], retries=PAYMENT_LINK_MAX_RETRIES)

    assert len(calls) == 1
    order = refresh(order)
    assert order.status == Order.Status.AWAITING_PAYMENT_METHOD
    assert build_reply_id("chk", "retry", order.pk) in reply_ids(
        last_outbound(conversation.contact)
    )


def test_link_task_ignores_a_superseded_attempt(conversation, tracked, online, payment_links):
    order = pending_order(conversation, tracked, quantity=1, checkout_attempt=2)

    send_payment_link.apply(args=[str(order.pk), 1])

    assert payment_links == []
    assert refresh(order).status == Order.Status.PENDING_PAYMENT


# --- Expiry -------------------------------------------------------------------------------------


def test_expire_checkouts_expires_overdue_checkouts(conversation, product):
    order = start(conversation, (product, 1))
    Order.objects.filter(pk=order.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

    assert expire_checkouts.apply().get() == 1

    order = refresh(order)
    assert order.status == Order.Status.EXPIRED
    assert order.expired_at is not None
    assert order.expires_at is None
    assert "expired" in last_outbound(conversation.contact).text


def test_expiry_cancels_the_link_first_and_releases_stock(conversation, tracked, cancelled_links):
    tracked.stock_qty = 3
    tracked.save()
    order = pending_order(
        conversation, tracked, quantity=2, expires_at=timezone.now() - timedelta(minutes=1)
    )
    link = PaymentLinkFactory(order=order)

    assert checkout.expire_checkouts() == 1

    assert cancelled_links == [link.pk]
    order = refresh(order)
    assert order.status == Order.Status.EXPIRED
    assert not order.stock_reserved
    assert stock(tracked) == 5
    assert "stock_released" in event_types(order)


def test_expiry_skips_an_order_whose_link_turned_out_paid(conversation, tracked, monkeypatch):
    order = pending_order(
        conversation, tracked, quantity=2, expires_at=timezone.now() - timedelta(minutes=1)
    )
    PaymentLinkFactory(order=order)

    def cancel_payment_link(payment_link):
        payment_link.status = "paid"
        payment_link.save()
        return payment_link

    monkeypatch.setattr(payment_services, "cancel_payment_link", cancel_payment_link)

    assert checkout.expire_checkouts() == 0
    assert refresh(order).status == Order.Status.PENDING_PAYMENT


def test_checkouts_before_their_deadline_are_kept(conversation, product):
    order = start(conversation, (product, 1))

    assert checkout.expire_checkouts() == 0
    assert refresh(order).status == Order.Status.AWAITING_ADDRESS


def test_expiry_runs_on_beat_every_five_minutes():
    from apps.orders.schedules import BEAT_SCHEDULE

    entry = BEAT_SCHEDULE["orders.expire_checkouts"]
    assert entry["task"] == "orders.expire_checkouts"
    assert entry["schedule"]._orig_minute == "*/5"


# --- Payment reminder ---------------------------------------------------------------------------


def unpaid_link(order, *, age_minutes=16, left_minutes=14, attempt=1):
    link = PaymentLinkFactory(
        order=order,
        reference_id=f"{order.number}-{attempt}",
        expires_at=timezone.now() + timedelta(minutes=left_minutes),
    )
    PaymentLink.objects.filter(pk=link.pk).update(
        created_at=timezone.now() - timedelta(minutes=age_minutes)
    )
    link.refresh_from_db()
    return link


def reminders(order) -> list[dict]:
    return [
        event.metadata for event in order.events.filter(type="reminder_sent").order_by("created_at")
    ]


def test_buyer_is_reminded_once_to_pay_an_open_link(conversation, tracked):
    order = pending_order(conversation, tracked, quantity=2)
    link = unpaid_link(order)

    assert send_payment_reminders.apply().get() == 1
    assert send_payment_reminders.apply().get() == 0

    assert [item["attempt"] for item in reminders(order)] == [1]
    message = last_outbound(conversation.contact)
    assert link.short_url in content_text(message)
    assert order.number in content_text(message)
    assert "notification_sent" in event_types(order)


def test_a_new_checkout_attempt_is_reminded_again(conversation, tracked):
    order = pending_order(conversation, tracked, quantity=1)
    unpaid_link(order).delete()
    OrderEventFactory(
        order=order,
        type="reminder_sent",
        actor="system",
        metadata={"reminder": "payment_reminder", "attempt": 1},
    )
    Order.objects.filter(pk=order.pk).update(checkout_attempt=2)
    unpaid_link(order, attempt=2)

    assert checkout.send_payment_reminders() == 1
    assert [item["attempt"] for item in reminders(order)] == [1, 2]


@pytest.mark.parametrize(
    ("age_minutes", "left_minutes"),
    [(5, 25), (26, 4)],
    ids=["link too new", "link about to expire"],
)
def test_no_reminder_outside_the_reminder_window(conversation, tracked, age_minutes, left_minutes):
    order = pending_order(conversation, tracked, quantity=1)
    unpaid_link(order, age_minutes=age_minutes, left_minutes=left_minutes)

    assert checkout.send_payment_reminders() == 0
    assert reminders(order) == []


def test_no_reminder_for_a_superseded_link_or_a_paid_order(conversation, tracked):
    stale = pending_order(conversation, tracked, quantity=1, checkout_attempt=2)
    unpaid_link(stale, attempt=1)
    paid = pending_order(conversation, tracked, quantity=1, status=Order.Status.CONFIRMED)
    unpaid_link(paid)

    assert checkout.send_payment_reminders() == 0


def test_payment_reminder_can_be_turned_off(conversation, tracked, settings):
    settings.ORDER_PAYMENT_REMINDER_MINUTES = 0
    order = pending_order(conversation, tracked, quantity=1)
    unpaid_link(order)

    assert checkout.send_payment_reminders() == 0


def test_payment_reminder_template_carries_the_link(conversation, tracked):
    order = pending_order(conversation, tracked, quantity=2)

    params = notifications.template_params(
        order, "payment_reminder", payment_url="https://rzp.io/i/abc"
    )

    assert params[1] == order.number
    assert params[3] == "https://rzp.io/i/abc"


def test_payment_reminders_run_on_beat_every_five_minutes():
    from apps.orders.schedules import BEAT_SCHEDULE

    entry = BEAT_SCHEDULE["orders.send_payment_reminders"]
    assert entry["task"] == send_payment_reminders.name
    assert entry["schedule"]._orig_minute == "*/5"


def test_sending_a_link_creates_the_default_reminder_template_once(
    conversation, tracked, online, payment_links, graph, django_capture_on_commit_callbacks
):
    order = pending_order(conversation, tracked, quantity=1)
    waba = conversation.phone_number.waba

    with django_capture_on_commit_callbacks(execute=True):
        send_payment_link.apply(args=[str(order.pk), 1])
    Order.objects.filter(pk=order.pk).update(checkout_attempt=2)
    with django_capture_on_commit_callbacks(execute=True):
        send_payment_link.apply(args=[str(order.pk), 2])

    template = MessageTemplate.objects.get(waba=waba, name="upc_payment_reminder")
    assert template.status == MessageTemplate.Status.PENDING
    assert template.category == "UTILITY"
    assert len(graph.calls_to("create_template")) == 1
    assert StoreSettings.objects.get(workspace=order.workspace).payment_reminder_template is None


def test_no_default_reminder_template_when_the_seller_mapped_one(
    conversation, store, tracked, online, payment_links, graph, django_capture_on_commit_callbacks
):
    store.payment_reminder_template = MessageTemplateFactory(
        waba=conversation.phone_number.waba, status=MessageTemplate.Status.APPROVED
    )
    store.save()
    order = pending_order(conversation, tracked, quantity=1)

    with django_capture_on_commit_callbacks(execute=True):
        send_payment_link.apply(args=[str(order.pk), 1])

    assert graph.calls_to("create_template") == []
