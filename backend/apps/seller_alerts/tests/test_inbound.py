"""Messages to the alerts number: verification, seller commands and order actions."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.factories import OrderFactory, StoreSettingsFactory
from apps.orders.models import Order
from apps.seller_alerts.factories import AlertRecipientFactory, PendingSellerReplyFactory
from apps.seller_alerts.inbound import ShipmentParseError, parse_shipment
from apps.seller_alerts.models import (
    AlertInboundMessage,
    AlertMessage,
    AlertRecipient,
    PendingSellerReply,
)
from apps.tenants.factories import WorkspaceFactory

from .conftest import body_of

pytestmark = pytest.mark.django_db


def reply_ids(message: dict) -> list[str]:
    interactive = message["interactive"]
    if interactive["type"] == "button":
        return [button["reply"]["id"] for button in interactive["action"]["buttons"]]
    return [row["id"] for section in interactive["action"]["sections"] for row in section["rows"]]


# --- Verification -------------------------------------------------------------------------------


@pytest.fixture
def pending(workspace, store):
    return AlertRecipientFactory(
        workspace=workspace,
        phone_e164="+919700000009",
        status=AlertRecipient.Status.PENDING,
        verified_at=None,
    )


def test_verify_button_verifies_and_lists_the_commands(
    pending, receive, fake_graph, frames, commit
):
    with commit():
        receive(
            pending.wa_id, type="button", text="Confirm", reply_id=f"upc:alerts:verify:{pending.pk}"
        )

    pending.refresh_from_db()
    assert pending.status == AlertRecipient.Status.VERIFIED
    assert pending.verified_at is not None
    assert pending.last_inbound_at is not None
    [reply] = fake_graph.sent_messages
    assert reply["to"] == pending.wa_id
    assert reply["type"] == "interactive"
    assert "order alerts for Sharma Sweets" in body_of(reply)
    assert "ORDERS" in body_of(reply) and "STOP" in body_of(reply)
    assert reply_ids(reply) == ["upc:alerts:orders"]
    assert [frame["data"] for frame in frames if frame["type"] == "alert_recipient.updated"] == [
        {"recipient_id": str(pending.pk), "status": "verified"}
    ]
    assert AlertInboundMessage.objects.get().outcome == AlertInboundMessage.Outcome.HANDLED
    assert AlertMessage.objects.get().kind == AlertMessage.Kind.REPLY


def test_verify_button_from_another_phone_is_ignored(pending, receive, fake_graph):
    receive("919811111111", type="button", reply_id=f"upc:alerts:verify:{pending.pk}")

    pending.refresh_from_db()
    assert pending.status == AlertRecipient.Status.PENDING
    assert fake_graph.sent_messages == []
    assert AlertInboundMessage.objects.get().outcome == AlertInboundMessage.Outcome.IGNORED


def test_unverified_senders_are_ignored(pending, order, orders_stub, receive, fake_graph):
    receive(pending.wa_id, text="ORDERS")
    receive(pending.wa_id, reply_id=f"upc:alerts:pack:{order.pk}", type="interactive")
    receive("919822222222", text="HELP")

    assert fake_graph.sent_messages == []
    assert orders_stub.calls == []
    assert set(AlertInboundMessage.objects.values_list("outcome", flat=True)) == {"ignored"}
    pending.refresh_from_db()
    assert pending.last_inbound_at is not None  # the window still opens


def test_duplicate_inbound_events_are_handled_once(
    recipient, order, orders_stub, receive, fake_graph
):
    event = receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:pack:{order.pk}")
    receive(recipient.wa_id, type="interactive", reply_id=event.reply_id, wamid=event.wamid)

    assert [call[0] for call in orders_stub.calls] == ["transition"]
    assert len(fake_graph.sent_messages) == 1
    assert AlertInboundMessage.objects.count() == 1


# --- Order actions ------------------------------------------------------------------------------


def test_mark_packed(recipient, order, orders_stub, receive, fake_graph):
    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:pack:{order.pk}")

    assert orders_stub.calls == [("transition", order.pk, "packed", "seller_whatsapp", "", "", "")]
    order.refresh_from_db()
    assert order.status == Order.Status.PACKED
    [reply] = fake_graph.sent_messages
    assert body_of(reply) == "Order SS-1001 is marked as packed."


def test_an_invalid_transition_gets_a_friendly_reply(
    recipient, order, orders_stub, receive, fake_graph
):
    order.status = Order.Status.SHIPPED
    order.save()

    receive(recipient.wa_id, type="button", reply_id=f"upc:alerts:pack:{order.pk}")

    [reply] = fake_graph.sent_messages
    assert body_of(reply) == "Order SS-1001 can't be marked as packed because it is shipped."


def test_cancel(recipient, order, orders_stub, receive, fake_graph):
    receive(recipient.wa_id, type="button", reply_id=f"upc:alerts:cancel:{order.pk}")

    assert orders_stub.calls == [
        ("cancel_order", order.pk, "seller_whatsapp", "Cancelled by the seller on WhatsApp")
    ]
    [reply] = fake_graph.sent_messages
    assert body_of(reply) == "Order SS-1001 is cancelled."


def test_another_workspaces_order_is_refused(
    recipient, other_workspace, orders_stub, receive, fake_graph
):
    foreign = OrderFactory(workspace=other_workspace)

    for action in ("pack", "ship", "cancel"):
        receive(recipient.wa_id, type="button", reply_id=f"upc:alerts:{action}:{foreign.pk}")
    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:orders:{foreign.pk}")

    assert orders_stub.calls == []
    assert not PendingSellerReply.objects.exists()
    assert len(fake_graph.sent_messages) == 4
    assert all(
        body_of(reply).startswith("This option is no longer available.")
        for reply in fake_graph.sent_messages
    )
    foreign.refresh_from_db()
    assert foreign.status == Order.Status.CONFIRMED


def test_ship_asks_for_courier_and_awb_then_ships(
    recipient, order, orders_stub, receive, fake_graph
):
    receive(recipient.wa_id, type="button", reply_id=f"upc:alerts:ship:{order.pk}")

    pending = PendingSellerReply.objects.get()
    assert (pending.order, pending.recipient) == (order, recipient)
    [prompt] = fake_graph.sent_messages
    assert pending.prompt_wamid == prompt["wamid"]
    assert "courier and AWB number for order SS-1001" in body_of(prompt)
    assert orders_stub.calls == []

    receive(recipient.wa_id, text="Blue Dart, 1234567890 https://bluedart.com/track/1234567890")

    assert orders_stub.calls == [
        (
            "transition",
            order.pk,
            "shipped",
            "seller_whatsapp",
            "Blue Dart",
            "1234567890",
            "https://bluedart.com/track/1234567890",
        )
    ]
    assert not PendingSellerReply.objects.exists()
    assert body_of(fake_graph.sent_messages[-1]) == (
        "Order SS-1001 is marked as shipped with Blue Dart (AWB 1234567890)."
    )


def test_an_unreadable_shipment_reply_keeps_waiting(
    recipient, order, orders_stub, receive, fake_graph
):
    PendingSellerReplyFactory(recipient=recipient, order=order)

    receive(recipient.wa_id, text="Delhivery")
    receive(recipient.wa_id, text="Delhivery 123456 http://track.example.com/123456")

    assert orders_stub.calls == []
    assert PendingSellerReply.objects.count() == 1
    first, second = (body_of(message) for message in fake_graph.sent_messages)
    assert first.startswith("Please send the courier name and the AWB number.")
    assert second.startswith("The tracking link must start with https://.")


def test_a_bare_reply_applies_to_the_order_that_asked_last(
    recipient, order, workspace, orders_stub, receive
):
    second_workspace = WorkspaceFactory()
    StoreSettingsFactory(workspace=second_workspace, store_name="Chai Craft")
    AlertRecipientFactory(workspace=second_workspace, phone_e164=recipient.phone_e164)
    second_order = OrderFactory(workspace=second_workspace, number="CC-1001")

    receive(recipient.wa_id, type="button", reply_id=f"upc:alerts:ship:{order.pk}")
    receive(recipient.wa_id, type="button", reply_id=f"upc:alerts:ship:{second_order.pk}")
    receive(recipient.wa_id, text="Delhivery 998877")

    assert orders_stub.calls == [
        ("transition", second_order.pk, "shipped", "seller_whatsapp", "Delhivery", "998877", "")
    ]
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED


def test_an_expired_shipment_request(recipient, order, orders_stub, receive, fake_graph):
    PendingSellerReplyFactory(
        recipient=recipient, order=order, expires_at=timezone.now() - timedelta(minutes=1)
    )

    receive(recipient.wa_id, text="Delhivery 998877")

    assert orders_stub.calls == []
    assert not PendingSellerReply.objects.exists()
    [reply] = fake_graph.sent_messages
    assert "order SS-1001 has expired" in body_of(reply)


def test_ship_when_the_order_cannot_ship(recipient, order, orders_stub, receive, fake_graph):
    order.status = Order.Status.DELIVERED
    order.save()

    receive(recipient.wa_id, type="button", reply_id=f"upc:alerts:ship:{order.pk}")

    assert not PendingSellerReply.objects.exists()
    [reply] = fake_graph.sent_messages
    assert body_of(reply) == "Order SS-1001 can't be marked as shipped because it is delivered."


# --- Commands -----------------------------------------------------------------------------------


def test_orders_lists_open_orders_across_workspaces(
    recipient, order, workspace, orders_stub, receive, fake_graph
):
    second_workspace = WorkspaceFactory()
    StoreSettingsFactory(workspace=second_workspace, store_name="Chai Craft")
    AlertRecipientFactory(workspace=second_workspace, phone_e164=recipient.phone_e164)
    second_order = OrderFactory(workspace=second_workspace, number="CC-1001")
    OrderFactory(workspace=workspace, status=Order.Status.DELIVERED)
    OrderFactory(workspace=WorkspaceFactory())  # not this phone's workspace
    unverified_workspace = WorkspaceFactory()
    AlertRecipientFactory(
        workspace=unverified_workspace,
        phone_e164=recipient.phone_e164,
        status=AlertRecipient.Status.PENDING,
    )
    OrderFactory(workspace=unverified_workspace)

    receive(recipient.wa_id, text=" orders ")

    [call] = orders_stub.calls
    assert call == ("open_orders_for_workspaces", {workspace.pk, second_workspace.pk}, 10)
    [reply] = fake_graph.sent_messages
    assert reply["interactive"]["type"] == "list"
    assert set(reply_ids(reply)) == {
        f"upc:alerts:orders:{order.pk}",
        f"upc:alerts:orders:{second_order.pk}",
    }
    rows = {
        row["title"]: row["description"]
        for section in reply["interactive"]["action"]["sections"]
        for row in section["rows"]
    }
    assert rows == {
        "SS-1001 · ₹498.00": "Confirmed · Sharma Sweets",
        "CC-1001 · ₹498.00": "Confirmed · Chai Craft",
    }


def test_orders_when_there_are_none(recipient, orders_stub, receive, fake_graph):
    receive(recipient.wa_id, type="button", reply_id="upc:alerts:orders")

    [reply] = fake_graph.sent_messages
    assert body_of(reply) == "You have no open orders right now."


def test_an_order_row_opens_its_actions(recipient, order, orders_stub, receive, fake_graph):
    order.status = Order.Status.PACKED
    order.save()

    receive(recipient.wa_id, type="interactive", reply_id=f"upc:alerts:orders:{order.pk}")

    [reply] = fake_graph.sent_messages
    assert body_of(reply).startswith("Order SS-1001 · Sharma Sweets\nStatus: Packed")
    assert reply_ids(reply) == [f"upc:alerts:ship:{order.pk}", f"upc:alerts:cancel:{order.pk}"]


@pytest.mark.parametrize("text", ["HELP", "help", "what is this?"])
def test_help_and_unknown_text_get_the_command_list(recipient, receive, fake_graph, text):
    receive(recipient.wa_id, text=text)

    [reply] = fake_graph.sent_messages
    assert "ORDERS" in body_of(reply) and "HELP" in body_of(reply)


def test_stop_opts_out(recipient, pending, receive, fake_graph, frames, commit):
    with commit():
        receive(recipient.wa_id, text="Stop")

    recipient.refresh_from_db()
    assert recipient.status == AlertRecipient.Status.OPTED_OUT
    assert recipient.opted_out_at is not None
    [reply] = fake_graph.sent_messages
    assert "won't get order alerts" in body_of(reply)
    assert [frame["data"] for frame in frames if frame["type"] == "alert_recipient.updated"] == [
        {"recipient_id": str(recipient.pk), "status": "opted_out"}
    ]

    receive(recipient.wa_id, text="ORDERS")

    assert len(fake_graph.sent_messages) == 1
    assert pending.status == AlertRecipient.Status.PENDING


def test_inbound_messages_open_the_window(recipient, receive):
    before = timezone.now()

    receive(recipient.wa_id, text="HELP")

    recipient.refresh_from_db()
    assert recipient.last_inbound_at >= before - timedelta(seconds=1)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Delhivery 1234567890", ("Delhivery", "1234567890", "")),
        (
            "Blue Dart 12345-678 https://bluedart.com/t?awb=1",
            ("Blue Dart", "12345-678", "https://bluedart.com/t?awb=1"),
        ),
        ("  India Post,  EE123456789IN ", ("India Post", "EE123456789IN", "")),
    ],
)
def test_parse_shipment(text, expected):
    shipment = parse_shipment(text)

    assert (shipment.courier_name, shipment.awb_number, shipment.tracking_url) == expected


@pytest.mark.parametrize(
    "text",
    ["", "1234567890", "Delhivery 12", "Delhivery 1234#5678", "Delhivery 123456 www.x.com/1"],
)
def test_parse_shipment_errors(text):
    with pytest.raises(ShipmentParseError):
        parse_shipment(text)
