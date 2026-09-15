"""Merchant order actions over the API: transitions, cancel, COD collected, refunded, notes."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.factories import ProductFactory
from apps.orders import services
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.orders.models import Order, OrderEvent
from apps.payments.factories import PaymentLinkFactory
from common import events
from common.roles import Role

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/orders/"


def url(order, action: str = "") -> str:
    return f"{ORDERS}{order.pk}/{action}"


def error(response) -> dict:
    return response.json()["error"]


@pytest.fixture
def broadcasts(monkeypatch):
    frames = []
    monkeypatch.setattr(
        "common.realtime.broadcast", lambda *args, **kwargs: frames.append((args, kwargs))
    )
    return frames


def test_agent_packs_a_confirmed_order(
    auth_client, workspace, broadcasts, django_capture_on_commit_callbacks
):
    order = OrderFactory(workspace=workspace)
    received = []

    def receiver(sender, event, **kwargs):
        received.append(event)

    events.order_status_changed.connect(receiver, dispatch_uid="orders-test-status")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client(Role.AGENT).post(
                url(order, "transition/"), {"to_status": "packed"}, format="json"
            )
    finally:
        events.order_status_changed.disconnect(dispatch_uid="orders-test-status")

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["status"] == "packed"
    assert data["packed_at"] is not None
    assert data["allowed_transitions"] == ["shipped", "cancelled"]
    event = order.events.get(type=OrderEvent.Type.STATUS_CHANGED)
    assert (event.from_status, event.to_status, event.actor) == ("confirmed", "packed", "dashboard")
    assert event.user_id is not None
    [changed] = received
    assert (changed.old_status, changed.new_status, changed.actor) == (
        "confirmed",
        "packed",
        "dashboard",
    )
    assert changed.actor_user_id == event.user_id
    assert any(args[1] == "order.updated" for args, _ in broadcasts)
    # No conversation and no mapped template: the buyer can't be told, and that is recorded.
    assert order.events.filter(type=OrderEvent.Type.NOTIFICATION_FAILED).exists()


def test_notify_buyer_false_sends_nothing(auth_client, workspace):
    order = OrderFactory(workspace=workspace)

    response = auth_client(Role.AGENT).post(
        url(order, "transition/"), {"to_status": "packed", "notify_buyer": False}, format="json"
    )

    assert response.status_code == 200, response.content
    assert not order.events.filter(type__startswith="notification").exists()


def test_shipping_needs_courier_and_awb(auth_client, workspace):
    order = OrderFactory(workspace=workspace)

    response = auth_client(Role.AGENT).post(
        url(order, "transition/"), {"to_status": "shipped"}, format="json"
    )

    assert response.status_code == 400, response.content
    details = json.dumps(error(response)["details"])
    assert "courier_name" in details
    assert "awb_number" in details
    assert Order.objects.get(pk=order.pk).status == "confirmed"


def test_shipping_records_tracking(auth_client, workspace):
    order = OrderFactory(workspace=workspace, status="packed")
    client = auth_client(Role.AGENT)
    body = {"to_status": "shipped", "courier_name": "Delhivery", "awb_number": "DL123"}

    insecure = client.post(
        url(order, "transition/"), {**body, "tracking_url": "http://x.example"}, format="json"
    )
    response = client.post(
        url(order, "transition/"),
        {**body, "tracking_url": "https://www.delhivery.com/track/DL123"},
        format="json",
    )

    assert insecure.status_code == 400
    assert response.status_code == 200, response.content
    data = response.json()
    assert (data["status"], data["courier_name"], data["awb_number"]) == (
        "shipped",
        "Delhivery",
        "DL123",
    )
    assert data["tracking_url"] == "https://www.delhivery.com/track/DL123"


def test_invalid_transition_is_409_with_the_allowed_moves(auth_client, workspace):
    order = OrderFactory(workspace=workspace)

    response = auth_client(Role.AGENT).post(
        url(order, "transition/"), {"to_status": "delivered"}, format="json"
    )

    assert response.status_code == 409, response.content
    assert error(response)["code"] == "invalid_order_transition"
    assert error(response)["details"] == {
        "from_status": "confirmed",
        "to_status": "delivered",
        "allowed": ["packed", "shipped", "cancelled"],
    }


def test_confirmed_only_from_needs_attention(auth_client, workspace):
    flagged = OrderFactory(workspace=workspace, status="needs_attention")
    packed = OrderFactory(workspace=workspace, status="packed")
    client = auth_client(Role.AGENT)

    ok = client.post(url(flagged, "transition/"), {"to_status": "confirmed"}, format="json")
    refused = client.post(url(packed, "transition/"), {"to_status": "confirmed"}, format="json")

    assert ok.status_code == 200, ok.content
    assert ok.json()["status"] == "confirmed"
    assert refused.status_code == 409


def test_cancel_restocks_and_cancels_the_open_link(
    auth_client, workspace, cancelled_links, django_capture_on_commit_callbacks
):
    product = ProductFactory(workspace=workspace, stock_qty=3)
    order = OrderFactory(
        workspace=workspace,
        status="pending_payment",
        payment_status="unpaid",
        stock_reserved=True,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    OrderItemFactory(order=order, product=product, quantity=2)
    link = PaymentLinkFactory(order=order)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(Role.AGENT).post(
            url(order, "cancel/"), {"reason": "Buyer asked", "notify_buyer": False}, format="json"
        )

    assert response.status_code == 200, response.content
    data = response.json()
    assert (data["status"], data["cancel_reason"]) == ("cancelled", "Buyer asked")
    assert data["cancelled_at"] is not None
    product.refresh_from_db()
    assert product.stock_qty == 5
    assert cancelled_links == [link.pk]
    assert not order.events.filter(type__startswith="notification").exists()
    assert order.events.filter(type=OrderEvent.Type.STOCK_RELEASED).exists()


def test_cancel_without_restock_keeps_the_stock_taken(auth_client, workspace):
    product = ProductFactory(workspace=workspace, stock_qty=3)
    order = OrderFactory(workspace=workspace, stock_reserved=True)
    OrderItemFactory(order=order, product=product, quantity=2)

    response = auth_client(Role.AGENT).post(
        url(order, "cancel/"), {"restock": False, "notify_buyer": False}, format="json"
    )

    assert response.status_code == 200, response.content
    product.refresh_from_db()
    assert product.stock_qty == 3
    assert Order.objects.get(pk=order.pk).stock_reserved is False


def test_shipped_orders_cannot_be_cancelled(auth_client, workspace):
    order = OrderFactory(workspace=workspace, status="shipped")

    response = auth_client(Role.AGENT).post(url(order, "cancel/"), {}, format="json")

    assert response.status_code == 409
    assert error(response)["code"] == "invalid_order_transition"


def test_mark_cod_collected(auth_client, workspace):
    cod = OrderFactory(
        workspace=workspace, status="delivered", payment_method="cod", payment_status="cod_pending"
    )
    online = OrderFactory(workspace=workspace, status="delivered")
    early = OrderFactory(
        workspace=workspace, status="confirmed", payment_method="cod", payment_status="cod_pending"
    )
    client = auth_client(Role.AGENT)

    response = client.post(url(cod, "mark-cod-collected/"), format="json")

    assert response.status_code == 200, response.content
    assert response.json()["payment_status"] == "cod_collected"
    assert cod.events.filter(type=OrderEvent.Type.COD_COLLECTED).exists()

    response = client.post(url(online, "mark-cod-collected/"), format="json")
    assert response.status_code == 409
    assert error(response)["code"] == "invalid_order_transition"
    assert error(response)["details"] == {
        "from_status": "delivered",
        "to_status": "cod_collected",
        "allowed": [],
    }
    response = client.post(url(early, "mark-cod-collected/"), format="json")
    assert response.status_code == 409
    assert error(response)["code"] == "invalid_order_transition"
    assert error(response)["details"]["allowed"] == ["packed", "shipped", "cancelled"]
    assert "cash-on-delivery" in error(response)["message"]


def test_mark_refunded_is_for_paid_orders_that_were_cancelled(auth_client, workspace):
    cancelled = OrderFactory(workspace=workspace, status="cancelled")
    confirmed = OrderFactory(workspace=workspace)
    client = auth_client(Role.ADMIN)

    response = client.post(url(cancelled, "mark-refunded/"), format="json")

    assert response.status_code == 200, response.content
    assert response.json()["payment_status"] == "refunded_manual"
    assert Order.objects.get(pk=cancelled.pk).refunded_at is not None

    response = client.post(url(confirmed, "mark-refunded/"), format="json")
    assert response.status_code == 409
    assert error(response)["code"] == "invalid_order_transition"
    assert error(response)["details"] == {
        "from_status": "confirmed",
        "to_status": "refunded_manual",
        "allowed": ["packed", "shipped", "cancelled"],
    }


def test_optional_action_fields_default_when_left_out(auth_client, workspace, monkeypatch):
    calls = {}

    def capture(name):
        def record(order, *args, **kwargs):
            calls[name] = kwargs
            return order

        return record

    monkeypatch.setattr(services, "transition", capture("transition"))
    monkeypatch.setattr(services, "cancel_order", capture("cancel_order"))
    order = OrderFactory(workspace=workspace)
    client = auth_client(Role.AGENT)

    response = client.post(url(order, "transition/"), {"to_status": "packed"}, format="json")
    assert response.status_code == 200, response.content
    assert client.post(url(order, "cancel/"), {}, format="json").status_code == 200
    assert calls["transition"]["notify_buyer"] is True
    assert {k: calls["cancel_order"][k] for k in ("reason", "restock", "notify_buyer")} == {
        "reason": "",
        "restock": True,
        "notify_buyer": True,
    }

    body = {"reason": "Out of stock", "restock": False, "notify_buyer": False}
    assert client.post(url(order, "cancel/"), body, format="json").status_code == 200
    assert {k: calls["cancel_order"][k] for k in body} == body


def test_optional_action_fields_are_optional_in_the_schema():
    from drf_spectacular.generators import SchemaGenerator

    schemas = SchemaGenerator().get_schema(request=None, public=True)["components"]["schemas"]
    for name, fields in {
        "OrderTransitionRequest": ("notify_buyer",),
        "CancelOrderRequest": ("reason", "restock", "notify_buyer"),
    }.items():
        schema = schemas[name]
        for field in fields:
            assert field not in schema.get("required", ())
            # openapi-typescript types a property with a default as required.
            assert "default" not in schema["properties"][field]


def test_notes_update_writes_one_event(auth_client, workspace):
    order = OrderFactory(workspace=workspace)
    client = auth_client(Role.AGENT)

    first = client.patch(url(order), {"notes": "Gift wrap, no invoice"}, format="json")
    client.patch(url(order), {"notes": "Gift wrap, no invoice"}, format="json")
    too_long = client.patch(url(order), {"notes": "x" * 2001}, format="json")

    assert first.status_code == 200, first.content
    assert first.json()["notes"] == "Gift wrap, no invoice"
    assert order.events.filter(type=OrderEvent.Type.NOTE).count() == 1
    assert too_long.status_code == 400


def test_open_orders_for_workspaces(workspace, other_workspace):
    now = timezone.now()
    older = OrderFactory(workspace=workspace, status="packed")
    newer = OrderFactory(workspace=other_workspace, status="needs_attention")
    OrderFactory(workspace=workspace, status="delivered")
    OrderFactory(workspace=workspace, status="awaiting_address")
    Order.objects.filter(pk=older.pk).update(created_at=now - timedelta(hours=2))
    Order.objects.filter(pk=newer.pk).update(created_at=now - timedelta(hours=1))

    orders = services.open_orders_for_workspaces([workspace.pk, other_workspace.pk])

    assert [order.pk for order in orders] == [newer.pk, older.pk]
    assert services.open_orders_for_workspaces([workspace.pk], limit=0) == []
