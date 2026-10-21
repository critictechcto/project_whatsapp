"""Advance or full payment per service (docs/contracts/booking-payments.md)."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.factories import ProductFactory
from apps.catalog.models import Product
from apps.offers import services as offers
from apps.orders import booking, buyer, checkout, notifications
from apps.orders.exceptions import CheckoutRejected
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.orders.models import Order, OrderEvent
from apps.seller_alerts import content as alert_content
from common.commerce import build_reply_id
from common.roles import Role

from .helpers import (
    content_text,
    event_types,
    expired_event,
    last_outbound,
    paid_event,
    press,
    refresh,
    reply_ids,
    start,
)

S = Order.Status
P = Order.PaymentStatus
ORDERS = "/api/v1/orders/"
db = pytest.mark.django_db


def service(**fields) -> Product:
    """An unsaved service for the pure requirement maths."""
    values = {"kind": Product.Kind.SERVICE, "price_paise": 49900}
    values.update(fields)
    return Product(**values)


def advance_amount(value):
    return {"booking_payment": "advance", "advance_type": "amount", "advance_value": value}


def advance_percent(value):
    return {"booking_payment": "advance", "advance_type": "percent", "advance_value": value}


# --- Requirement maths (no database) -----------------------------------------------------------


def test_strictest_line_wins():
    plain, part, full = service(), service(**advance_amount(10000)), service(booking_payment="full")

    assert checkout.booking_requirement([(plain, 1, 49900)], 49900) == ("store_default", 0)
    assert checkout.booking_requirement([(plain, 1, 49900), (part, 1, 49900)], 99800) == (
        "advance",
        10000,
    )
    assert checkout.booking_requirement(
        [(plain, 1, 49900), (part, 1, 49900), (full, 1, 49900)], 149700
    ) == ("full", 0)


def test_line_advances_amount_per_person_and_percent_rounded_up():
    per_person = service(**advance_amount(10000))
    percent = service(**advance_percent(15))

    assert per_person.advance_for_line(2, 99800) == 20000
    assert percent.advance_for_line(1, 49999) == 7500  # ceil(7499.85)
    assert checkout.booking_requirement([(per_person, 2, 99800), (percent, 1, 49999)], 149799) == (
        "advance",
        27500,
    )


def test_advance_is_capped_below_the_total_and_full_when_it_reaches_it():
    part = service(**advance_amount(40000))

    # Two people at ₹400 each against a ₹600 total after a discount: becomes full.
    assert checkout.booking_requirement([(part, 2, 99800)], 60000) == ("full", 0)
    assert checkout.booking_requirement([(part, 1, 49900)], 40050) == ("advance", 39950)
    assert checkout.booking_requirement([(part, 1, 49900)], 40000) == ("full", 0)


def test_products_and_deleted_lines_do_not_count():
    assert checkout.booking_requirement([(None, 1, 49900)], 49900) == ("store_default", 0)


# --- Labels and notes (no database) ------------------------------------------------------------


def booking_order(**fields) -> Order:
    values = {
        "kind": Order.Kind.BOOKING,
        "total_paise": 49900,
        "payment_method": Order.PaymentMethod.ONLINE,
    }
    values.update(fields)
    return Order(**values)


def test_booking_payment_notes():
    shop = booking_order(payment_method="pay_at_shop", payment_status=P.COD_PENDING)
    advance = booking_order(payment_status=P.ADVANCE_PAID, amount_paid_paise=10000)

    assert notifications.booking_payment_note(shop) == (
        "Pay at the shop after your service: ₹499.00."
    )
    assert notifications.booking_payment_note(advance) == (
        "Advance ₹100.00 paid. Pay the rest, ₹399.00, at the shop."
    )
    for status in (P.PAID, P.COD_COLLECTED):
        assert notifications.booking_payment_note(booking_order(payment_status=status)) == (
            "Your booking is paid."
        )
    for status in (P.UNPAID, P.REFUNDED_MANUAL):
        assert notifications.booking_payment_note(booking_order(payment_status=status)) == (
            "Payment pending."
        )


def test_advance_paid_labels_for_buyer_and_seller():
    order = booking_order(payment_status=P.ADVANCE_PAID, amount_paid_paise=10000)

    assert order.balance_due_paise == 39900
    assert buyer.payment_label(order) == "Advance ₹100.00 paid, ₹399.00 at the shop"
    assert alert_content.payment_label(order) == "Advance ₹100.00 paid, ₹399.00 at the shop"
    assert notifications.payment_phrase(order) == "Advance ₹100.00 paid, ₹399.00 at the shop"


def test_cancelled_text_for_advance_and_paid():
    advance = booking_order(payment_status=P.ADVANCE_PAID, amount_paid_paise=10000)

    assert notifications.cancelled_payment_text(advance) == (
        " The store will contact you about your advance."
    )
    assert notifications.cancelled_payment_text(booking_order(payment_status=P.PAID)) == (
        " The store will refund your payment."
    )
    assert notifications.cancelled_payment_text(booking_order(payment_status=P.UNPAID)) == ""


def test_balance_due_never_goes_negative():
    assert booking_order(amount_paid_paise=60000).balance_due_paise == 0


# --- Checkout ------------------------------------------------------------------------------------


@pytest.fixture
def plain(workspace):
    return ProductFactory(workspace=workspace, service=True, name="Haircut", price_paise=49900)


@pytest.fixture
def with_advance(workspace):
    return ProductFactory(
        workspace=workspace,
        service=True,
        name="Bridal makeup",
        price_paise=49900,
        **advance_amount(10000),
    )


@pytest.fixture
def full_only(workspace):
    return ProductFactory(
        workspace=workspace,
        service=True,
        name="Spa day",
        price_paise=49900,
        booking_payment="full",
    )


def tomorrow(workspace):
    return booking.local_now(workspace).date() + timedelta(days=1)


def to_payment_choice(conversation, service):
    order = start(conversation, (service, 1))
    press(
        conversation,
        build_reply_id("chk", "day", order.pk, booking.day_arg(tomorrow(conversation.workspace))),
    )
    press(conversation, build_reply_id("chk", "win", order.pk, 0))
    return refresh(order)


def pay_id(order, method):
    return build_reply_id("chk", "pay", order.pk, method)


@db
def test_advance_booking_offers_advance_or_full(conversation, store, with_advance, online):
    order = to_payment_choice(conversation, with_advance)

    assert (order.booking_payment, order.advance_paise) == ("advance", 10000)
    choice = last_outbound(conversation.contact)
    assert reply_ids(choice) == [
        pay_id(order, "advance"),
        pay_id(order, "online"),
        build_reply_id("chk", "cancel", order.pk),
    ]
    text = content_text(choice)
    assert "Pay ₹100 advance" in text
    assert "Pay ₹499 in full" in text
    assert "Pay ₹100.00 now to book. The rest, ₹399.00, is paid at the shop." in text
    assert "Pay at the shop" not in text
    assert "Cancellation policy" not in text


@db
def test_full_payment_booking_offers_only_online(conversation, store, full_only, online):
    order = to_payment_choice(conversation, full_only)

    assert (order.booking_payment, order.advance_paise) == ("full", 0)
    choice = last_outbound(conversation.contact)
    assert reply_ids(choice) == [pay_id(order, "online"), build_reply_id("chk", "cancel", order.pk)]
    assert "Full payment is needed to book." in content_text(choice)


@db
def test_store_default_keeps_shop_and_shows_the_cancellation_policy(
    conversation, store, plain, online
):
    store.booking_cancellation_policy = "Free cancellation up to 24 hours before."
    store.save()
    order = to_payment_choice(conversation, plain)

    choice = last_outbound(conversation.contact)
    assert reply_ids(choice) == [
        pay_id(order, "online"),
        pay_id(order, "shop"),
        build_reply_id("chk", "cancel", order.pk),
    ]
    text = content_text(choice)
    assert "How would you like to pay?" in text
    assert "Cancellation policy: Free cancellation up to 24 hours before." in text


@db
@pytest.mark.parametrize("fixture", ["with_advance", "full_only"])
def test_online_payment_is_required_without_a_gateway(conversation, store, fixture, request):
    service = request.getfixturevalue(fixture)

    with pytest.raises(CheckoutRejected) as caught:
        start(conversation, (service, 1))

    assert caught.value.reason == "payment_unavailable"
    assert not Order.objects.exists()
    assert checkout.ONLINE_REQUIRED_TEXT in content_text(last_outbound(conversation.contact))
    assert checkout.ONLINE_REQUIRED_TEXT == (
        "This service needs online payment to book, and the store can't take online payments "
        "right now. Please contact the store."
    )


@db
def test_choices_that_the_requirement_does_not_allow_are_stale(
    conversation, store, with_advance, plain, online
):
    order = to_payment_choice(conversation, with_advance)

    press(conversation, pay_id(order, "shop"))

    assert refresh(order).status == S.AWAITING_PAYMENT_METHOD
    assert checkout.STALE_TEXT in content_text(last_outbound(conversation.contact))

    other = to_payment_choice(conversation, plain)
    press(conversation, pay_id(other, "advance"))

    assert refresh(other).status == S.AWAITING_PAYMENT_METHOD
    assert checkout.STALE_TEXT in content_text(last_outbound(conversation.contact))


@db
def test_paying_the_advance(
    conversation,
    store,
    with_advance,
    online,
    payment_links,
    django_capture_on_commit_callbacks,
):
    order = to_payment_choice(conversation, with_advance)

    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, pay_id(order, "advance"))

    order = refresh(order)
    assert (order.status, order.payment_method, order.pay_advance) == (
        S.PENDING_PAYMENT,
        "online",
        True,
    )
    [call] = payment_links
    assert call["amount_paise"] == 10000
    created = order.events.get(type=OrderEvent.Type.PAYMENT_LINK_CREATED)
    assert created.metadata["amount_paise"] == 10000
    assert "₹100.00" in created.detail
    assert "Pay ₹100.00" in content_text(last_outbound(conversation.contact))

    checkout.on_payment_link_paid(paid_event(order.payment_links.get()))

    order = refresh(order)
    assert (order.status, order.payment_status) == (S.REQUESTED, P.ADVANCE_PAID)
    assert (order.amount_paid_paise, order.balance_due_paise) == (10000, 39900)
    assert "received your booking request" in content_text(last_outbound(conversation.contact))


@db
def test_paying_in_full_on_an_advance_booking(
    conversation,
    store,
    with_advance,
    online,
    payment_links,
    django_capture_on_commit_callbacks,
):
    order = to_payment_choice(conversation, with_advance)

    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, pay_id(order, "online"))
    [call] = payment_links
    assert call["amount_paise"] == 49900

    checkout.on_payment_link_paid(paid_event(refresh(order).payment_links.get()))

    order = refresh(order)
    assert (order.status, order.payment_status) == (S.REQUESTED, P.PAID)
    assert (order.amount_paid_paise, order.balance_due_paise) == (49900, 0)


@db
def test_try_again_keeps_the_advance(
    conversation,
    store,
    with_advance,
    online,
    payment_links,
    django_capture_on_commit_callbacks,
):
    order = to_payment_choice(conversation, with_advance)
    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, pay_id(order, "advance"))

    checkout.on_payment_link_closed(expired_event(refresh(order).payment_links.get()), expired=True)

    order = refresh(order)
    assert order.status == S.AWAITING_PAYMENT_METHOD
    assert reply_ids(last_outbound(conversation.contact)) == [
        build_reply_id("chk", "retry", order.pk),
        build_reply_id("chk", "cancel", order.pk),
    ]
    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, build_reply_id("chk", "retry", order.pk))

    assert [call["amount_paise"] for call in payment_links] == [10000, 10000]


@db
def test_a_paid_full_booking_sets_amount_paid(
    conversation,
    store,
    plain,
    online,
    payment_links,
    django_capture_on_commit_callbacks,
):
    order = to_payment_choice(conversation, plain)
    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, pay_id(order, "online"))

    checkout.on_payment_link_paid(paid_event(refresh(order).payment_links.get()))

    order = refresh(order)
    assert (order.payment_status, order.amount_paid_paise) == (P.PAID, 49900)


@db
def test_an_offer_recomputes_the_requirement(conversation, store, workspace, online, monkeypatch):
    nearly_all = ProductFactory(
        workspace=workspace, service=True, price_paise=49900, **advance_amount(45000)
    )
    applied = offers.AppliedOffer(claim_id=uuid.uuid4(), code="DIWALI", discount_paise=5000)
    monkeypatch.setattr(offers, "apply_to_checkout", lambda order: applied)

    order = start(conversation, (nearly_all, 1))

    assert order.total_paise == 44900
    assert (order.booking_payment, order.advance_paise) == ("full", 0)


@db
def test_an_offer_claimed_at_the_payment_step_resends_the_new_advance(
    conversation, store, workspace, online, monkeypatch
):
    percent = ProductFactory(
        workspace=workspace, service=True, price_paise=50000, **advance_percent(20)
    )
    order = to_payment_choice(conversation, percent)
    assert order.advance_paise == 10000
    applied = offers.AppliedOffer(claim_id=uuid.uuid4(), code="BIG", discount_paise=41000)
    monkeypatch.setattr(offers, "apply_to_checkout", lambda order: applied)

    assert checkout.apply_offer_to_active_checkout(conversation.pk) is True

    order = refresh(order)
    assert order.total_paise == 9000
    assert (order.booking_payment, order.advance_paise) == ("full", 0)
    assert reply_ids(last_outbound(conversation.contact)) == [
        pay_id(order, "online"),
        build_reply_id("chk", "cancel", order.pk),
    ]


# --- Balance at the shop -------------------------------------------------------------------------


def advance_booking(workspace, **fields) -> Order:
    values = {
        "workspace": workspace,
        "kind": Order.Kind.BOOKING,
        "status": S.CONFIRMED,
        "payment_method": Order.PaymentMethod.ONLINE,
        "payment_status": P.ADVANCE_PAID,
        "address": None,
        "subtotal_paise": 49900,
        "total_paise": 49900,
        "booking_payment": "advance",
        "advance_paise": 10000,
        "amount_paid_paise": 10000,
        "appointment_at": timezone.now() + timedelta(days=1),
    }
    values.update(fields)
    order = OrderFactory(**values)
    OrderItemFactory(order=order, unit_price_paise=49900, quantity=1)
    return order


@db
def test_mark_balance_paid(auth_client, workspace):
    order = advance_booking(workspace)

    response = auth_client(Role.AGENT).post(f"{ORDERS}{order.pk}/mark-balance-paid/")

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["payment_status"] == "paid"
    assert (data["amount_paid_paise"], data["balance_due_paise"]) == (10000, 0)
    order = refresh(order)
    assert order.cod_collected_at is not None
    event = order.events.get(type=OrderEvent.Type.BALANCE_COLLECTED)
    assert event.detail == "Balance ₹399.00 paid at the shop."
    assert "balance_collected" in event_types(order)


@db
@pytest.mark.parametrize(
    "fields",
    [
        {"status": S.REQUESTED},
        {"payment_status": P.PAID, "amount_paid_paise": 49900},
        {"payment_status": P.COD_PENDING, "payment_method": "pay_at_shop"},
    ],
)
def test_mark_balance_paid_needs_an_advance_paid_confirmed_booking(auth_client, workspace, fields):
    order = advance_booking(workspace, **fields)

    response = auth_client(Role.AGENT).post(f"{ORDERS}{order.pk}/mark-balance-paid/")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_order_transition"
    assert refresh(order).payment_status == fields.get("payment_status", P.ADVANCE_PAID)


@db
def test_viewers_cannot_mark_balance_paid(auth_client, workspace):
    order = advance_booking(workspace, status=S.COMPLETED)

    response = auth_client(Role.VIEWER).post(f"{ORDERS}{order.pk}/mark-balance-paid/")

    assert response.status_code == 403
    assert refresh(order).payment_status == P.ADVANCE_PAID


@db
def test_order_api_shows_the_money_fields(auth_client, workspace):
    order = advance_booking(workspace)

    client = auth_client(Role.VIEWER)
    listed = client.get(ORDERS).json()["results"][0]
    detail = client.get(f"{ORDERS}{order.pk}/").json()

    for data in (listed, detail):
        assert data["payment_status"] == "advance_paid"
        assert (data["advance_paise"], data["amount_paid_paise"], data["balance_due_paise"]) == (
            10000,
            10000,
            39900,
        )


@db
def test_advance_paid_bookings_can_be_marked_refunded_once_cancelled(auth_client, workspace):
    order = advance_booking(workspace, status=S.CANCELLED)

    response = auth_client(Role.ADMIN).post(f"{ORDERS}{order.pk}/mark-refunded/")

    assert response.status_code == 200, response.content
    assert response.json()["payment_status"] == "refunded_manual"


# --- Store settings ------------------------------------------------------------------------------


@db
def test_cancellation_policy_is_a_store_setting(auth_client, workspace):
    client = auth_client(Role.ADMIN)

    response = client.patch(
        "/api/v1/store/settings/",
        {"booking_cancellation_policy": "  No refunds within 6 hours.  "},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["booking_cancellation_policy"] == "No refunds within 6 hours."
    too_long = client.patch(
        "/api/v1/store/settings/", {"booking_cancellation_policy": "x" * 301}, format="json"
    )
    assert too_long.status_code == 400
