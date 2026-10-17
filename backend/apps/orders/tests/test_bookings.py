"""Bookings (services): day and window, pay at the shop or online, confirm, reminders, offers."""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.catalog.factories import ProductFactory
from apps.inbox.factories import ConversationFactory
from apps.inbox.models import Message
from apps.message_templates.factories import MessageTemplateFactory, standard_components
from apps.message_templates.models import MessageTemplate
from apps.offers import services as offers
from apps.orders import booking, buyer, checkout, lifecycle, services, store_setup
from apps.orders.exceptions import CheckoutRejected
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.orders.models import Order, OrderEvent
from common.commerce import build_reply_id
from common.roles import Role

from .helpers import (
    content_text,
    event_types,
    interactive_type,
    last_outbound,
    outbound,
    paid_event,
    press,
    refresh,
    reply_ids,
    start,
    typed,
)

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/orders/"
S = Order.Status


@pytest.fixture
def haircut(workspace):
    return ProductFactory(
        workspace=workspace, service=True, name="Haircut", price_paise=49900, duration_minutes=45
    )


@pytest.fixture
def offer(monkeypatch):
    """``offers.apply_to_checkout`` returns a ₹50 DIWALI claim."""
    applied = offers.AppliedOffer(claim_id=uuid.uuid4(), code="DIWALI", discount_paise=5000)
    monkeypatch.setattr(offers, "apply_to_checkout", lambda order: applied)
    return applied


def tomorrow(workspace):
    return booking.local_now(workspace).date() + timedelta(days=1)


def day_id(order, day) -> str:
    return build_reply_id("chk", "day", order.pk, booking.day_arg(day))


def win_id(order, index) -> str:
    return build_reply_id("chk", "win", order.pk, index)


def to_payment_choice(conversation, service):
    order = start(conversation, (service, 1))
    press(conversation, day_id(order, tomorrow(conversation.workspace)))
    press(conversation, win_id(order, 0))
    return refresh(order)


def booked(conversation, service, *, status=S.CONFIRMED, appointment_at=None, **fields) -> Order:
    values = {
        "workspace": conversation.workspace,
        "contact": conversation.contact,
        "phone_number": conversation.phone_number,
        "conversation": conversation,
        "kind": Order.Kind.BOOKING,
        "status": status,
        "payment_method": Order.PaymentMethod.PAY_AT_SHOP,
        "payment_status": Order.PaymentStatus.COD_PENDING,
        "address": None,
        "item_count": 1,
        "subtotal_paise": service.price_paise,
        "total_paise": service.price_paise,
        "requested_date": tomorrow(conversation.workspace),
        "requested_window": {"label": "Morning", "start": "09:00", "end": "12:00"},
        "appointment_at": appointment_at,
        "confirmed_at": timezone.now() - timedelta(days=3),
    }
    values.update(fields)
    order = OrderFactory(**values)
    OrderItemFactory(
        order=order,
        product=service,
        sku=service.sku,
        name=service.name,
        unit_price_paise=service.price_paise,
        quantity=1,
    )
    return order


def local(workspace, day, hour, minute=0):
    return datetime.combine(day, datetime.min.time().replace(hour=hour, minute=minute)).replace(
        tzinfo=booking.workspace_zone(workspace)
    )


# --- Checkout ------------------------------------------------------------------------------------


def test_booking_day_window_and_pay_at_the_shop(conversation, store, haircut):
    order = start(conversation, (haircut, 1))

    assert (order.kind, order.status) == (Order.Kind.BOOKING, S.AWAITING_TIME)
    assert (order.shipping_paise, order.total_paise, order.address) == (0, 49900, None)
    days = last_outbound(conversation.contact)
    assert interactive_type(days) == "list"
    day = tomorrow(conversation.workspace)
    assert day_id(order, day) in reply_ids(days)

    press(conversation, day_id(order, day))
    windows = last_outbound(conversation.contact)
    assert interactive_type(windows) == "button"
    assert reply_ids(windows) == [win_id(order, 0), win_id(order, 1), win_id(order, 2)]
    assert refresh(order).requested_date == day

    press(conversation, win_id(order, 1))
    order = refresh(order)
    assert order.status == S.AWAITING_PAYMENT_METHOD
    assert order.requested_window == {"label": "Afternoon", "start": "12:00", "end": "16:00"}
    choice = last_outbound(conversation.contact)
    assert reply_ids(choice) == [
        build_reply_id("chk", "pay", order.pk, "shop"),
        build_reply_id("chk", "cancel", order.pk),
    ]
    assert "Afternoon" in content_text(choice)

    press(conversation, build_reply_id("chk", "pay", order.pk, "shop"))
    order = refresh(order)
    assert order.status == S.REQUESTED
    assert order.payment_method == Order.PaymentMethod.PAY_AT_SHOP
    assert order.payment_status == Order.PaymentStatus.COD_PENDING
    assert (order.cod_fee_paise, order.total_paise) == (0, 49900)
    assert "received your booking request" in content_text(last_outbound(conversation.contact))
    assert OrderEvent.Type.TIME_REQUESTED in event_types(order)


def test_more_than_three_windows_are_a_list(conversation, store, haircut):
    store.booking_windows = [
        {"label": f"Slot {n}", "start": f"{9 + n:02d}:00", "end": f"{10 + n:02d}:00"}
        for n in range(5)
    ]
    store.save()
    order = start(conversation, (haircut, 1))

    press(conversation, day_id(order, tomorrow(conversation.workspace)))

    message = last_outbound(conversation.contact)
    assert interactive_type(message) == "list"
    assert reply_ids(message) == [win_id(order, n) for n in range(5)]


def test_a_day_that_is_not_open_resends_the_days(conversation, store, haircut):
    order = start(conversation, (haircut, 1))
    before = len(outbound(conversation.contact))

    press(conversation, build_reply_id("chk", "day", order.pk, "20200101"))

    assert refresh(order).requested_date is None
    message = last_outbound(conversation.contact)
    assert len(outbound(conversation.contact)) == before + 1
    assert interactive_type(message) == "list"
    assert "no longer available" in content_text(message)


def test_a_window_without_a_day_resends_the_days(conversation, store, haircut):
    order = start(conversation, (haircut, 1))

    press(conversation, win_id(order, 0))

    assert refresh(order).status == S.AWAITING_TIME
    assert interactive_type(last_outbound(conversation.contact)) == "list"


def test_a_window_after_the_time_step_is_stale(conversation, store, haircut):
    order = to_payment_choice(conversation, haircut)

    press(conversation, win_id(order, 2))

    assert refresh(order).requested_window["label"] == "Morning"
    assert checkout.STALE_TEXT in content_text(last_outbound(conversation.contact))


def test_online_paid_booking_becomes_a_request(
    conversation, store, haircut, online, payment_links, django_capture_on_commit_callbacks
):
    store.pay_at_shop_enabled = False
    store.save()
    order = to_payment_choice(conversation, haircut)
    assert reply_ids(last_outbound(conversation.contact))[0] == build_reply_id(
        "chk", "pay", order.pk, "online"
    )

    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, build_reply_id("chk", "pay", order.pk, "online"))
    order = refresh(order)
    assert order.status == S.PENDING_PAYMENT
    [call] = payment_links
    assert call["amount_paise"] == 49900
    assert call["description"].startswith(f"Booking {order.number}")

    link = order.payment_links.get()
    checkout.on_payment_link_paid(paid_event(link))

    order = refresh(order)
    assert (order.status, order.payment_status) == (S.REQUESTED, Order.PaymentStatus.PAID)
    assert "received your booking request" in content_text(last_outbound(conversation.contact))


def test_mixed_cart_is_rejected(conversation, store, haircut, product):
    with pytest.raises(CheckoutRejected) as caught:
        start(conversation, (product, 1), (haircut, 1))

    assert caught.value.reason == "mixed_cart"
    assert not Order.objects.exists()
    assert "can't be checked out together" in content_text(last_outbound(conversation.contact))


def test_booking_without_any_payment_option_is_rejected(conversation, store, haircut):
    store.pay_at_shop_enabled = False
    store.save()

    with pytest.raises(CheckoutRejected) as caught:
        start(conversation, (haircut, 1))

    assert caught.value.reason == "payment_unavailable"
    assert not Order.objects.exists()


def test_bookings_ignore_the_minimum_order(conversation, store, haircut):
    store.min_order_paise = 99900
    store.save()

    assert start(conversation, (haircut, 1)).status == S.AWAITING_TIME


def test_expiry_includes_choosing_a_time(conversation, store, haircut):
    order = start(conversation, (haircut, 1))
    Order.objects.filter(pk=order.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

    assert checkout.expire_checkouts() == 1

    assert refresh(order).status == S.EXPIRED


# --- Offers --------------------------------------------------------------------------------------


def test_offer_discount_is_applied_at_checkout(conversation, store, haircut, offer):
    order = start(conversation, (haircut, 1))

    assert (order.discount_paise, order.offer_code, order.offer_claim_id) == (
        5000,
        "DIWALI",
        offer.claim_id,
    )
    assert order.total_paise == 49900 - 5000
    assert OrderEvent.Type.OFFER_APPLIED in event_types(order)
    assert f"DIWALI {buyer.MINUS}₹50.00" in content_text(last_outbound(conversation.contact))


def test_discounted_delivery_totals_and_payment_link_amount(
    conversation, store, product, offer, online, payment_links, django_capture_on_commit_callbacks
):
    store.shipping_fee_paise = 4900
    store.free_shipping_above_paise = None
    store.cod_enabled = True
    store.cod_fee_paise = 2000
    store.save()
    order = start(conversation, (product, 2))
    assert order.total_paise == 49800 - 5000 + 4900
    Order.objects.filter(pk=order.pk).update(
        status=S.AWAITING_PAYMENT_METHOD,
        address={"city": "Pune", "pincode": "411001"},
    )

    with django_capture_on_commit_callbacks(execute=True):
        press(conversation, build_reply_id("chk", "pay", order.pk, "online"))

    assert refresh(order).total_paise == 49800 - 5000 + 4900
    assert payment_links[0]["amount_paise"] == 49800 - 5000 + 4900


def test_discounted_cash_on_delivery_total(conversation, store, product, offer):
    store.shipping_fee_paise = 4900
    store.free_shipping_above_paise = None
    store.cod_enabled = True
    store.cod_fee_paise = 2000
    store.save()
    order = start(conversation, (product, 2))
    Order.objects.filter(pk=order.pk).update(status=S.AWAITING_PAYMENT_METHOD)

    press(conversation, build_reply_id("chk", "pay", order.pk, "cod"))

    order = refresh(order)
    assert order.status == S.CONFIRMED
    assert order.total_paise == 49800 - 5000 + 4900 + 2000


def test_offer_claimed_later_resends_the_payment_choice(conversation, store, haircut, monkeypatch):
    order = to_payment_choice(conversation, haircut)
    before = len(outbound(conversation.contact))
    applied = offers.AppliedOffer(claim_id=uuid.uuid4(), code="WELCOME", discount_paise=9900)
    monkeypatch.setattr(offers, "apply_to_checkout", lambda order: applied)

    assert services.apply_offer_to_active_checkout(conversation.pk) is True

    order = refresh(order)
    assert (order.discount_paise, order.total_paise) == (9900, 40000)
    messages = outbound(conversation.contact)
    assert len(messages) == before + 1
    assert "Offer WELCOME applied" in content_text(messages[-1])
    assert build_reply_id("chk", "pay", order.pk, "shop") in reply_ids(messages[-1])
    # The same offer again changes nothing.
    assert services.apply_offer_to_active_checkout(conversation.pk) is False
    assert len(outbound(conversation.contact)) == before + 1


def test_offer_claimed_while_choosing_a_time_updates_quietly(
    conversation, store, haircut, monkeypatch
):
    order = start(conversation, (haircut, 1))
    before = len(outbound(conversation.contact))
    applied = offers.AppliedOffer(claim_id=uuid.uuid4(), code="WELCOME", discount_paise=9900)
    monkeypatch.setattr(offers, "apply_to_checkout", lambda order: applied)

    assert services.apply_offer_to_active_checkout(conversation.pk) is True

    assert refresh(order).total_paise == 40000
    assert len(outbound(conversation.contact)) == before


def test_no_checkout_no_offer(conversation, store, offer):
    assert services.apply_offer_to_active_checkout(conversation.pk) is False


def test_offer_code_text_is_not_an_address(workspace, store, number, product, monkeypatch):
    from apps.contacts.factories import ContactFactory

    contact = ContactFactory(workspace=workspace, phone_e164="+14155550123")
    conversation = ConversationFactory(
        workspace=workspace, contact=contact, phone_number=number, window_open=True
    )
    start(conversation, (product, 1))
    monkeypatch.setattr(offers, "match_code", lambda workspace_id, text: object())

    assert services.handle_checkout_text(typed(conversation, "DIWALI")) is False


# --- Merchant actions ----------------------------------------------------------------------------


def test_confirm_and_reschedule_notify_the_buyer(auth_client, conversation, store, haircut):
    order = booked(conversation, haircut, status=S.REQUESTED)
    day = tomorrow(conversation.workspace)
    client = auth_client(Role.AGENT)

    response = client.post(
        f"{ORDERS}{order.pk}/confirm-booking/",
        {"appointment_at": local(conversation.workspace, day, 10, 30).isoformat()},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "confirmed"
    message = last_outbound(conversation.contact)
    assert "is confirmed" in message.text
    assert "10:30 AM" in message.text

    Order.objects.filter(pk=order.pk).update(
        reminder_sent_at=timezone.now(),
        day_before_reminder_sent_at=timezone.now(),
        reschedule_requested_at=timezone.now(),
    )
    response = client.post(
        f"{ORDERS}{order.pk}/confirm-booking/",
        {"appointment_at": local(conversation.workspace, day, 15).isoformat()},
        format="json",
    )

    assert response.status_code == 200, response.content
    order = refresh(order)
    assert order.reminder_sent_at is None
    assert order.day_before_reminder_sent_at is None
    assert order.reschedule_requested_at is None
    assert "has changed" in last_outbound(conversation.contact).text
    assert "3:00 PM" in last_outbound(conversation.contact).text
    assert event_types(order).count(OrderEvent.Type.APPOINTMENT_SET) == 2


def test_confirm_booking_rejects_deliveries(auth_client, workspace):
    order = OrderFactory(workspace=workspace)

    response = auth_client(Role.AGENT).post(
        f"{ORDERS}{order.pk}/confirm-booking/",
        {"appointment_at": timezone.now().isoformat()},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_order_transition"


def test_booking_cannot_be_confirmed_without_a_time(auth_client, conversation, store, haircut):
    order = booked(conversation, haircut, status=S.REQUESTED)

    response = auth_client(Role.AGENT).post(
        f"{ORDERS}{order.pk}/transition/", {"to_status": "confirmed"}, format="json"
    )

    assert response.status_code == 409


@pytest.mark.parametrize("to_status", ["completed", "no_show"])
def test_bookings_complete_or_no_show(auth_client, conversation, store, haircut, to_status):
    order = booked(conversation, haircut, appointment_at=timezone.now() - timedelta(hours=1))

    response = auth_client(Role.AGENT).post(
        f"{ORDERS}{order.pk}/transition/",
        {"to_status": to_status, "notify_buyer": False},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert refresh(order).status == to_status


def test_mark_paid_at_the_shop(auth_client, conversation, store, haircut):
    order = booked(conversation, haircut, status=S.COMPLETED, appointment_at=timezone.now())

    response = auth_client(Role.AGENT).post(f"{ORDERS}{order.pk}/mark-cod-collected/")

    assert response.status_code == 200, response.content
    assert refresh(order).payment_status == Order.PaymentStatus.COD_COLLECTED


def test_list_filters_by_kind(auth_client, conversation, store, haircut, workspace):
    delivery = OrderFactory(workspace=workspace)
    appointment = booked(conversation, haircut, status=S.REQUESTED)
    client = auth_client(Role.VIEWER)

    bookings = client.get(ORDERS, {"kind": "booking"}).json()["results"]
    deliveries = client.get(ORDERS, {"kind": "delivery"}).json()["results"]

    assert [item["id"] for item in bookings] == [str(appointment.pk)]
    assert [item["id"] for item in deliveries] == [str(delivery.pk)]
    assert bookings[0]["kind"] == "booking"


# --- Reminders -----------------------------------------------------------------------------------


def reminder_events(order) -> list:
    return list(
        order.events.filter(type=OrderEvent.Type.REMINDER_SENT).values_list(
            "metadata__reminder", flat=True
        )
    )


def test_hours_before_reminder_is_sent_once(conversation, store, haircut):
    store.booking_day_before_reminder = False
    store.save()
    now = timezone.now()
    order = booked(conversation, haircut, appointment_at=now + timedelta(hours=2))

    assert lifecycle.send_booking_reminders(now=now) == 1
    assert lifecycle.send_booking_reminders(now=now + timedelta(minutes=10)) == 0

    order = refresh(order)
    assert order.reminder_sent_at == now
    assert reminder_events(order) == ["booking_reminder"]
    message = last_outbound(conversation.contact)
    assert "Pay at the shop after your service: ₹499.00." in message.text
    assert reply_ids(message) == [
        build_reply_id("ord", "attend", order.pk),
        build_reply_id("ord", "resched", order.pk),
        build_reply_id("ord", "bcancel", order.pk),
    ]


def test_paid_bookings_are_reminded_without_the_shop_line(conversation, store, haircut):
    now = timezone.now()
    booked(
        conversation,
        haircut,
        appointment_at=now + timedelta(hours=2),
        payment_method=Order.PaymentMethod.ONLINE,
        payment_status=Order.PaymentStatus.PAID,
    )

    assert lifecycle.send_booking_reminders(now=now) == 1

    text = last_outbound(conversation.contact).text
    assert "Pay at the shop" not in text
    assert "Your booking is paid." in text


def test_reminders_off_sends_nothing(conversation, store, haircut):
    store.booking_reminder_hours = 0
    store.booking_day_before_reminder = False
    store.save()
    now = timezone.now()
    booked(conversation, haircut, appointment_at=now + timedelta(hours=1))

    assert lifecycle.send_booking_reminders(now=now) == 0


def test_day_before_and_hours_before_reminders_are_sent_once_each(conversation, store, haircut):
    workspace = conversation.workspace
    day = tomorrow(workspace)
    appointment = local(workspace, day, 10, 30)
    order = booked(conversation, haircut, appointment_at=appointment)
    lifecycle.record_event(order, OrderEvent.Type.APPOINTMENT_SET, actor="dashboard")
    OrderEvent.objects.filter(order=order).update(created_at=appointment - timedelta(days=3))
    evening = local(workspace, day - timedelta(days=1), 18, 5)

    assert lifecycle.send_booking_reminders(now=evening - timedelta(hours=1)) == 0
    assert lifecycle.send_booking_reminders(now=evening) == 1
    assert lifecycle.send_booking_reminders(now=evening + timedelta(minutes=10)) == 0
    order = refresh(order)
    assert order.day_before_reminder_sent_at == evening
    assert order.reminder_sent_at is None
    assert "see you tomorrow" in last_outbound(conversation.contact).text

    morning = appointment - timedelta(hours=2)
    assert lifecycle.send_booking_reminders(now=morning) == 1
    assert lifecycle.send_booking_reminders(now=morning + timedelta(minutes=10)) == 0
    order = refresh(order)
    assert order.reminder_sent_at == morning
    assert reminder_events(order) == ["booking_day_before", "booking_reminder"]


def test_day_before_is_skipped_when_booked_too_late(conversation, store, haircut):
    workspace = conversation.workspace
    day = tomorrow(workspace)
    appointment = local(workspace, day, 10, 30)
    order = booked(conversation, haircut, appointment_at=appointment)
    evening = local(workspace, day - timedelta(days=1), 18, 5)
    lifecycle.record_event(order, OrderEvent.Type.APPOINTMENT_SET, actor="dashboard")
    OrderEvent.objects.filter(order=order).update(created_at=evening - timedelta(hours=3))

    assert lifecycle.send_booking_reminders(now=evening) == 0
    assert refresh(order).day_before_reminder_sent_at is None


def test_day_before_is_skipped_once_the_day_has_come(conversation, store, haircut):
    store.booking_reminder_hours = 1
    store.save()
    workspace = conversation.workspace
    day = tomorrow(workspace)
    appointment = local(workspace, day, 10, 30)
    order = booked(conversation, haircut, appointment_at=appointment)
    lifecycle.record_event(order, OrderEvent.Type.APPOINTMENT_SET, actor="dashboard")
    OrderEvent.objects.filter(order=order).update(created_at=appointment - timedelta(days=3))

    assert lifecycle.send_booking_reminders(now=local(workspace, day, 7)) == 0
    assert refresh(order).day_before_reminder_sent_at is None


REMINDER_BODY = (
    "Hi {{1}}, a reminder of booking {{2}} for {{3}} at {{4}}. {{5}} Tap a button below please."
)


def reminder_template(number, *, buttons=True):
    components = standard_components(REMINDER_BODY)
    if buttons:
        components.append(
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": text}
                    for text in ("I'll be there", "Change time", "Cancel booking")
                ],
            }
        )
    return MessageTemplateFactory(
        waba=number.waba,
        name="upc_booking_reminder",
        status=MessageTemplate.Status.APPROVED,
        components=components,
    )


def test_reminder_template_carries_quick_reply_payloads(workspace, store, number, haircut):
    store.booking_reminder_template = reminder_template(number)
    store.save()
    conversation = ConversationFactory(workspace=workspace, phone_number=number)
    now = timezone.now()
    order = booked(conversation, haircut, appointment_at=now + timedelta(hours=2))

    assert lifecycle.send_booking_reminders(now=now) == 1

    message = last_outbound(conversation.contact)
    assert message.type == Message.Type.TEMPLATE
    components = message.payload["template"]["components"]
    body = next(c for c in components if c["type"] == "body")
    assert body["parameters"][4]["text"] == "Pay at the shop after your service: ₹499.00."
    buttons = [c for c in components if c["type"] == "button"]
    assert [(b["sub_type"], b["index"]) for b in buttons] == [
        ("quick_reply", "0"),
        ("quick_reply", "1"),
        ("quick_reply", "2"),
    ]
    assert [b["parameters"][0] for b in buttons] == [
        {"type": "payload", "payload": build_reply_id("ord", action, order.pk)}
        for action in ("attend", "resched", "bcancel")
    ]


def test_reminder_template_without_buttons_is_sent_without_payloads(
    workspace, store, number, haircut
):
    store.booking_reminder_template = reminder_template(number, buttons=False)
    store.save()
    conversation = ConversationFactory(workspace=workspace, phone_number=number)
    now = timezone.now()
    booked(conversation, haircut, appointment_at=now + timedelta(hours=2))

    assert lifecycle.send_booking_reminders(now=now) == 1

    message = last_outbound(conversation.contact)
    assert message.type == Message.Type.TEMPLATE
    assert "button" not in json.dumps(message.payload)


def test_starter_reminder_template_has_three_quick_replies():
    starter = next(s for s in store_setup.STARTER_TEMPLATES if s.name == "upc_booking_reminder")
    [body, buttons] = store_setup.starter_components(starter)
    assert body["text"].count("{{") == store_setup.TEMPLATE_PARAM_COUNTS["booking_reminder"]
    assert [b["text"] for b in buttons["buttons"]] == [
        "I'll be there",
        "Change time",
        "Cancel booking",
    ]


# --- Reminder buttons ----------------------------------------------------------------------------


@pytest.fixture
def confirmed(conversation, store, haircut):
    return booked(
        conversation,
        haircut,
        appointment_at=local(conversation.workspace, tomorrow(conversation.workspace), 10, 30),
    )


def test_attend(conversation, confirmed):
    press(conversation, build_reply_id("ord", "attend", confirmed.pk))

    order = refresh(confirmed)
    assert order.attendance_confirmed_at is not None
    assert OrderEvent.Type.ATTENDANCE_CONFIRMED in event_types(order)
    assert "Thanks, see you on" in last_outbound(conversation.contact).text
    assert "10:30 AM" in last_outbound(conversation.contact).text


def test_change_time(conversation, confirmed):
    press(conversation, build_reply_id("ord", "resched", confirmed.pk))

    order = refresh(confirmed)
    assert order.reschedule_requested_at is not None
    assert OrderEvent.Type.RESCHEDULE_REQUESTED in event_types(order)
    assert "Tell us a day and time" in last_outbound(conversation.contact).text


def test_cancel_asks_first_then_cancels_as_the_buyer(conversation, confirmed):
    press(conversation, build_reply_id("ord", "bcancel", confirmed.pk))

    question = last_outbound(conversation.contact)
    assert f"Cancel booking {confirmed.number}?" in question.text.replace(
        f" ({booking.appointment_text(confirmed)})", ""
    )
    assert reply_ids(question) == [
        build_reply_id("ord", "bcancel_yes", confirmed.pk),
        build_reply_id("ord", "bcancel_no", confirmed.pk),
    ]
    assert refresh(confirmed).status == S.CONFIRMED

    press(conversation, build_reply_id("ord", "bcancel_yes", confirmed.pk))

    order = refresh(confirmed)
    assert order.status == S.CANCELLED
    change = order.events.filter(type=OrderEvent.Type.STATUS_CHANGED).last()
    assert change.actor == OrderEvent.Actor.BUYER
    assert "is cancelled" in last_outbound(conversation.contact).text


def test_keep_the_booking(conversation, confirmed):
    press(conversation, build_reply_id("ord", "bcancel_no", confirmed.pk))

    assert refresh(confirmed).status == S.CONFIRMED
    assert "stays as it is" in last_outbound(conversation.contact).text


@pytest.mark.parametrize("action", ["attend", "resched", "bcancel", "bcancel_yes"])
def test_answers_on_a_booking_that_is_not_confirmed_are_stale(conversation, store, haircut, action):
    order = booked(conversation, haircut, status=S.REQUESTED)

    press(conversation, build_reply_id("ord", action, order.pk))

    order = refresh(order)
    assert order.status == S.REQUESTED
    assert order.attendance_confirmed_at is None
    assert order.reschedule_requested_at is None
    assert checkout.STALE_TEXT in content_text(last_outbound(conversation.contact))


def test_answers_for_someone_elses_booking_are_stale(conversation, store, haircut, workspace):
    other = ConversationFactory(workspace=workspace, phone_number=conversation.phone_number)
    order = booked(other, haircut, appointment_at=timezone.now() + timedelta(days=1))

    press(conversation, build_reply_id("ord", "bcancel_yes", order.pk))

    assert refresh(order).status == S.CONFIRMED


def test_reminder_answers_are_not_handled_twice(conversation, confirmed):
    message = press(conversation, build_reply_id("ord", "attend", confirmed.pk))
    sent = len(outbound(conversation.contact))

    press(conversation, build_reply_id("ord", "attend", confirmed.pk), message=message)

    assert len(outbound(conversation.contact)) == sent
