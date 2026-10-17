"""Booking requests: the ``new_booking`` alert and its *Accept* / *Cancel* actions.

The booking fields on ``Order`` (``kind``, ``requested_date``, ``requested_window``,
``appointment_at``) land in apps.orders separately. Until then the ``booking`` fixture supplies
them as class-level defaults, so these tests run before and after that change.
"""

import importlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.orders import services as order_services
from apps.orders.exceptions import InvalidOrderTransition
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.orders.models import Order
from apps.seller_alerts import content, services, tasks
from apps.seller_alerts.factories import AlertRecipientFactory
from apps.seller_alerts.models import AlertMessage, default_alert_events
from common.events import emit, order_status_changed

from .conftest import body_of
from .test_alerts import button_payloads, status_event, template_params
from .test_inbound import reply_ids

pytestmark = pytest.mark.django_db

HAS_BOOKING_FIELDS = hasattr(Order, "kind")
REQUESTED_DATE = date(2026, 10, 24)
WINDOW = {"label": "Morning", "start": "09:00", "end": "12:00"}
IST = ZoneInfo("Asia/Kolkata")
WINDOW_START = datetime(2026, 10, 24, 9, 0, tzinfo=IST)
DAY = content.format_day(REQUESTED_DATE)


@pytest.fixture
def booking_fields(monkeypatch):
    """Before apps.orders has the booking fields, give every order booking defaults."""
    if not HAS_BOOKING_FIELDS:
        monkeypatch.setattr(Order, "kind", "booking", raising=False)
        monkeypatch.setattr(Order, "requested_date", REQUESTED_DATE, raising=False)
        monkeypatch.setattr(Order, "requested_window", dict(WINDOW), raising=False)
        monkeypatch.setattr(Order, "appointment_at", None, raising=False)


@pytest.fixture
def booking(workspace, store, booking_fields):
    fields = (
        {
            "kind": "booking",
            "requested_date": REQUESTED_DATE,
            "requested_window": dict(WINDOW),
            "address": None,
        }
        if HAS_BOOKING_FIELDS
        else {}
    )
    order = OrderFactory(workspace=workspace, number="SS-2001", status="requested", **fields)
    order.contact.name = "Priya Sharma"
    order.contact.save()
    OrderItemFactory(order=order, name="Haircut", quantity=1, unit_price_paise=49800)
    return order


@pytest.fixture
def fire(commit):
    def fire(event):
        with commit():
            assert emit(order_status_changed, event) == []

    return fire


@pytest.fixture
def confirm_calls(monkeypatch):
    """``orders.services.confirm_booking`` stand-in: records the call and confirms."""
    calls = []

    def confirm_booking(order, *, appointment_at, actor, user=None):
        calls.append((order.pk, appointment_at, actor))
        if order.status != "requested":
            raise InvalidOrderTransition(order.status, "confirmed", [])
        order.status = Order.Status.CONFIRMED
        order.appointment_at = appointment_at
        order.save()
        return order

    monkeypatch.setattr(order_services, "confirm_booking", confirm_booking)
    return calls


# --- Triggers -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("pending_payment", "requested", "new_booking"),
        ("awaiting_payment_method", "requested", "new_booking"),
        ("awaiting_time", "requested", "new_booking"),
        ("", "requested", "new_booking"),
        ("needs_attention", "requested", None),
        ("requested", "confirmed", None),
        ("requested", "requested", None),
        ("confirmed", "completed", None),
    ],
)
def test_booking_requests_alert_as_new_booking(order, old, new, expected):
    assert services.alert_event_for(status_event(order, old, new, "buyer")) == expected


def test_new_recipients_get_booking_alerts_by_default():
    assert "new_booking" in default_alert_events()


def test_migration_subscribes_new_order_recipients(workspace):
    migration = importlib.import_module("apps.seller_alerts.migrations.0003_new_booking_alert")
    gets_orders = AlertRecipientFactory(
        workspace=workspace, events=["new_order", "needs_attention"]
    )
    no_orders = AlertRecipientFactory(workspace=workspace, events=["needs_attention"])

    migration.subscribe_new_order_recipients(django_apps, None)

    gets_orders.refresh_from_db()
    no_orders.refresh_from_db()
    assert gets_orders.events == ["new_order", "new_booking", "needs_attention"]
    assert no_orders.events == ["needs_attention"]


def test_a_booking_never_sends_new_order(booking, recipient, fake_graph):
    result = tasks.send_alert.apply(
        args=[str(recipient.pk), str(booking.pk), "new_order", "confirmed", "system"]
    ).get()

    assert result == "skipped"
    assert fake_graph.sent_messages == []


# --- Delivery -----------------------------------------------------------------------------------


def test_new_booking_uses_the_template_outside_the_window(booking, recipient, fake_graph, fire):
    fire(status_event(booking, "pending_payment", "requested", "system"))

    [sent] = fake_graph.sent_messages
    assert sent["to"] == recipient.wa_id
    assert sent["template"]["name"] == "upc_new_booking"
    assert template_params(sent) == [
        "Sharma Sweets",
        "SS-2001",
        "Priya Sharma",
        "1 x Haircut",
        f"{DAY}, Morning (09:00-12:00)",
        "Paid online",
    ]
    assert button_payloads(sent) == [
        f"upc:alerts:accept:{booking.pk}",
        f"upc:alerts:cancel:{booking.pk}",
    ]
    message = AlertMessage.objects.get()
    assert (message.kind, message.status) == ("new_booking", AlertMessage.Status.SENT)


def test_new_booking_is_free_form_inside_the_window(booking, recipient, fake_graph, fire):
    recipient.last_inbound_at = timezone.now()
    recipient.save()

    fire(status_event(booking, "pending_payment", "requested", "system"))

    [sent] = fake_graph.sent_messages
    assert sent["type"] == "interactive"
    assert "New booking request at Sharma Sweets" in body_of(sent)
    assert reply_ids(sent) == [
        f"upc:alerts:accept:{booking.pk}",
        f"upc:alerts:cancel:{booking.pk}",
    ]


def test_only_recipients_subscribed_to_bookings(workspace, store, booking, fake_graph, fire):
    AlertRecipientFactory(workspace=workspace, events=["new_order"])
    subscribed = AlertRecipientFactory(workspace=workspace, events=["new_booking"])

    fire(status_event(booking, "pending_payment", "requested", "system"))

    assert [sent["to"] for sent in fake_graph.sent_messages] == [subscribed.wa_id]


def test_booking_content_says_pay_at_the_shop(booking):
    booking.payment_method = "pay_at_shop"
    booking.payment_status = "cod_pending"

    outbound = content.new_booking(booking, "Glow Salon")

    assert outbound.template_params[-1] == "Pay at the shop"
    assert outbound.template is content.NEW_BOOKING


# --- Accept -------------------------------------------------------------------------------------


def test_accept_confirms_at_the_window_start(
    booking, recipient, confirm_calls, receive, fake_graph
):
    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:accept:{booking.pk}")

    assert confirm_calls == [(booking.pk, WINDOW_START, "seller_whatsapp")]
    [reply] = fake_graph.sent_messages
    assert body_of(reply) == (
        f"Booking SS-2001 is confirmed for {DAY}, 09:00. The customer will be told."
    )


def test_accept_uses_the_workspace_time_zone(workspace, booking, recipient, confirm_calls, receive):
    workspace.time_zone = "Asia/Dubai"
    workspace.save()

    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:accept:{booking.pk}")

    [(_, appointment_at, _)] = confirm_calls
    assert appointment_at == datetime(2026, 10, 24, 9, 0, tzinfo=ZoneInfo("Asia/Dubai"))


@pytest.mark.parametrize("status", ["confirmed", "cancelled"])
def test_accept_on_a_handled_booking_is_stale(
    booking, recipient, confirm_calls, receive, fake_graph, status
):
    booking.status = status
    booking.save()

    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:accept:{booking.pk}")

    assert confirm_calls == []
    [reply] = fake_graph.sent_messages
    assert "no longer available" in body_of(reply)


def test_accept_on_a_delivery_order_is_stale(order, recipient, confirm_calls, receive, fake_graph):
    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:accept:{order.pk}")

    assert confirm_calls == []
    assert "no longer available" in body_of(fake_graph.sent_messages[0])


def test_accept_from_another_workspace_is_stale(
    other_workspace, booking, confirm_calls, receive, fake_graph
):
    stranger = AlertRecipientFactory(workspace=other_workspace, phone_e164="+919700000077")

    receive(stranger.wa_id, type="interactive", reply_id=f"upc:alerts:accept:{booking.pk}")

    assert confirm_calls == []
    assert "no longer available" in body_of(fake_graph.sent_messages[0])


def test_accept_reports_a_refused_confirmation(
    booking, recipient, monkeypatch, receive, fake_graph
):
    def refuse(order, *, appointment_at, actor, user=None):
        raise InvalidOrderTransition("cancelled", "confirmed", [])

    monkeypatch.setattr(order_services, "confirm_booking", refuse)

    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:accept:{booking.pk}")

    assert "can't be confirmed" in body_of(fake_graph.sent_messages[0])


def test_cancel_on_a_booking_asks_about_the_booking(
    booking, recipient, orders_stub, receive, fake_graph, monkeypatch
):
    monkeypatch.setattr(Order, "allowed_transitions", property(lambda self: ["cancelled"]))

    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:cancel:{booking.pk}")

    [reply] = fake_graph.sent_messages
    assert body_of(reply) == "Cancel booking SS-2001? The customer will be told."
    assert reply_ids(reply) == [
        f"upc:alerts:cancel_yes:{booking.pk}",
        f"upc:alerts:cancel_no:{booking.pk}",
    ]


# --- Order list and details ---------------------------------------------------------------------


def test_order_list_shows_the_requested_time(booking):
    outbound = content.order_list([booking], {booking.workspace_id: "Sharma Sweets"})

    [row] = outbound.interactive["action"]["sections"][0]["rows"]
    assert row["description"] == f"Requested · {DAY}, Morning (09:00-12:00)"


def test_order_list_shows_the_appointment_once_confirmed(booking):
    booking.status = Order.Status.CONFIRMED
    booking.appointment_at = datetime(2026, 10, 24, 10, 30, tzinfo=IST)

    outbound = content.order_list([booking], {})

    [row] = outbound.interactive["action"]["sections"][0]["rows"]
    assert row["description"] == f"Confirmed · {DAY}, 10:30"


def test_booking_details_offer_accept(booking, monkeypatch):
    monkeypatch.setattr(
        Order, "allowed_transitions", property(lambda self: ["confirmed", "cancelled"])
    )

    outbound = content.order_details(booking, "Sharma Sweets")

    assert outbound.body.splitlines() == [
        "Booking SS-2001 · Sharma Sweets",
        "Status: Requested",
        "Customer: Priya Sharma",
        "Services: 1 x Haircut",
        f"Requested: {DAY}, Morning (09:00-12:00)",
        "Total: ₹498.00 (Paid online)",
    ]
    assert reply_ids(outbound.free_form_message()) == [
        f"upc:alerts:accept:{booking.pk}",
        f"upc:alerts:cancel:{booking.pk}",
    ]
