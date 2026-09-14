import itertools
from dataclasses import dataclass, field

import pytest
from django.conf import settings
from django.utils import timezone

from apps.orders import services as order_services
from apps.orders.exceptions import InvalidOrderTransition
from apps.orders.factories import OrderFactory, OrderItemFactory, StoreSettingsFactory
from apps.orders.models import Order
from apps.seller_alerts.factories import AlertRecipientFactory
from common import realtime
from common.events import PlatformInboundMessage, emit, platform_inbound_message_received

_wamids = itertools.count(1)


@pytest.fixture
def frames(monkeypatch):
    """Realtime frames sent during the test (use with ``commit``)."""
    sent: list[dict] = []
    monkeypatch.setattr(realtime, "_send", lambda group, frame: sent.append(frame))
    return sent


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """``with commit():`` runs on_commit callbacks (task dispatch, frames) when the block exits."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


@pytest.fixture
def store(workspace):
    return StoreSettingsFactory(workspace=workspace, store_name="Sharma Sweets", order_prefix="SS")


@pytest.fixture
def recipient(workspace, store):
    return AlertRecipientFactory(workspace=workspace, name="Ravi", phone_e164="+919700000001")


@pytest.fixture
def order(workspace, store):
    order = OrderFactory(workspace=workspace, number="SS-1001")
    OrderItemFactory(order=order, name="Kaju Katli 250 g", quantity=2, unit_price_paise=24900)
    return order


def inbound_event(
    from_wa_id: str,
    *,
    text: str | None = None,
    reply_id: str | None = None,
    type: str = "text",
    wamid: str | None = None,
    timestamp=None,
) -> PlatformInboundMessage:
    return PlatformInboundMessage(
        phone_number_id=settings.PLATFORM_WA_PHONE_NUMBER_ID,
        wamid=wamid or f"wamid.INBOUND{next(_wamids):08d}",
        from_wa_id=from_wa_id,
        timestamp=timestamp or timezone.now(),
        type=type,
        text=text,
        reply_id=reply_id,
    )


@pytest.fixture
def receive(fake_graph):
    """``receive(wa_id, text=..., reply_id=...)`` emits a PlatformInboundMessage."""

    def send(from_wa_id: str, **kwargs) -> PlatformInboundMessage:
        event = inbound_event(from_wa_id, **kwargs)
        assert emit(platform_inbound_message_received, event) == []
        return event

    return send


def body_of(message: dict) -> str:
    if message["type"] == "interactive":
        return message["interactive"]["body"]["text"]
    if message["type"] == "text":
        return message["text"]["body"]
    raise AssertionError(f"No body in a {message['type']} message")


@dataclass
class OrdersStub:
    calls: list[tuple] = field(default_factory=list)


@pytest.fixture
def orders_stub(monkeypatch):
    """Stand-ins for the orders services with the frozen signatures (B3 implements the real
    ones). Transitions follow the contract table and are saved; calls are recorded."""
    stub = OrdersStub()

    def transition(
        order,
        to_status,
        *,
        actor,
        user=None,
        courier_name="",
        awb_number="",
        tracking_url="",
        notify_buyer=True,
    ):
        stub.calls.append(
            ("transition", order.pk, to_status, actor, courier_name, awb_number, tracking_url)
        )
        if to_status not in order.allowed_transitions:
            raise InvalidOrderTransition(order.status, to_status, order.allowed_transitions)
        order.status = to_status
        order.courier_name, order.awb_number, order.tracking_url = (
            courier_name,
            awb_number,
            tracking_url,
        )
        order.save()
        return order

    def cancel_order(order, *, actor, user=None, reason="", restock=True, notify_buyer=True):
        stub.calls.append(("cancel_order", order.pk, actor, reason))
        if Order.Status.CANCELLED not in order.allowed_transitions:
            raise InvalidOrderTransition(
                order.status, Order.Status.CANCELLED, order.allowed_transitions
            )
        order.status = Order.Status.CANCELLED
        order.cancel_reason = reason
        order.save()
        return order

    def open_orders_for_workspaces(workspace_ids, *, limit=10):
        stub.calls.append(("open_orders_for_workspaces", set(workspace_ids), limit))
        return list(
            Order.objects.filter(
                workspace_id__in=list(workspace_ids), status__in=Order.OPEN_STATUSES
            ).order_by("-created_at")[:limit]
        )

    monkeypatch.setattr(order_services, "transition", transition)
    monkeypatch.setattr(order_services, "cancel_order", cancel_order)
    monkeypatch.setattr(order_services, "open_orders_for_workspaces", open_orders_for_workspaces)
    return stub
