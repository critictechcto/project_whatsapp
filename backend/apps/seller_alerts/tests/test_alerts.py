"""Order alerts: triggers, recipients, idempotency and the free-form/template cost rule."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.factories import OrderEventFactory, OrderFactory, OrderItemFactory
from apps.orders.models import Order, OrderEvent
from apps.seller_alerts import content, services, tasks
from apps.seller_alerts.factories import AlertRecipientFactory
from apps.seller_alerts.models import AlertMessage, AlertRecipient
from apps.whatsapp.client.errors import OutsideWindowError, TransientError
from common.events import OrderStatusChanged, emit, order_status_changed

from .conftest import body_of

pytestmark = pytest.mark.django_db


def status_event(order, old_status, new_status, actor="system") -> OrderStatusChanged:
    return OrderStatusChanged(
        workspace_id=order.workspace_id,
        order_id=order.pk,
        order_number=order.number,
        contact_id=order.contact_id,
        phone_number_id=order.phone_number_id,
        old_status=old_status,
        new_status=new_status,
        payment_status=order.payment_status,
        payment_method=order.payment_method,
        total_paise=order.total_paise,
        actor=actor,
        actor_user_id=None,
        occurred_at=timezone.now(),
    )


@pytest.fixture
def fire(commit):
    def fire(event: OrderStatusChanged) -> None:
        with commit():
            assert emit(order_status_changed, event) == []

    return fire


def template_params(message: dict) -> list[str]:
    [body] = [c for c in message["template"]["components"] if c["type"] == "body"]
    return [parameter["text"] for parameter in body["parameters"]]


def button_payloads(message: dict) -> list[str]:
    return [
        c["parameters"][0]["payload"]
        for c in message["template"]["components"]
        if c["type"] == "button"
    ]


@pytest.mark.parametrize(
    ("old", "new", "actor", "expected"),
    [
        ("pending_payment", "confirmed", "system", "new_order"),
        ("awaiting_payment_method", "confirmed", "buyer", "new_order"),
        ("", "confirmed", "buyer", "new_order"),
        ("needs_attention", "confirmed", "dashboard", None),
        ("pending_payment", "needs_attention", "system", "needs_attention"),
        ("pending_payment", "cancelled", "system", "order_cancelled"),
        ("confirmed", "cancelled", "buyer", "order_cancelled"),
        ("confirmed", "cancelled", "dashboard", None),
        ("packed", "cancelled", "seller_whatsapp", None),
        ("pending_payment", "expired", "system", None),
        ("confirmed", "packed", "dashboard", None),
        ("confirmed", "confirmed", "system", None),
    ],
)
def test_which_changes_alert(order, old, new, actor, expected):
    assert services.alert_event_for(status_event(order, old, new, actor)) == expected


def test_new_order_uses_the_template_outside_the_window(recipient, order, fake_graph, fire):
    fire(status_event(order, "pending_payment", "confirmed"))

    [sent] = fake_graph.sent_messages
    assert sent["to"] == recipient.wa_id
    assert sent["type"] == "template"
    assert sent["template"]["name"] == "upc_new_order"
    assert template_params(sent) == [
        "Sharma Sweets",
        "SS-1001",
        "2 x Kaju Katli 250 g",
        "₹498.00",
        "Paid online",
    ]
    assert button_payloads(sent) == [
        f"upc:alerts:pack:{order.pk}",
        f"upc:alerts:ship:{order.pk}",
        f"upc:alerts:cancel:{order.pk}",
    ]
    message = AlertMessage.objects.get()
    assert message.kind == AlertMessage.Kind.NEW_ORDER
    assert message.status == AlertMessage.Status.SENT
    assert (message.order, message.recipient, message.workspace) == (
        order,
        recipient,
        order.workspace,
    )
    assert message.payload["mode"] == "template"
    recipient.refresh_from_db()
    assert recipient.last_sent_at is not None


def test_new_order_is_free_form_inside_the_window(recipient, order, fake_graph, fire):
    recipient.last_inbound_at = timezone.now() - timedelta(hours=23)
    recipient.save()

    fire(status_event(order, "pending_payment", "confirmed"))

    [sent] = fake_graph.sent_messages
    assert sent["type"] == "interactive"
    interactive = sent["interactive"]
    assert interactive["type"] == "button"
    assert body_of(sent) == content.NEW_ORDER.render(
        ["Sharma Sweets", "SS-1001", "2 x Kaju Katli 250 g", "₹498.00", "Paid online"]
    )
    assert [
        (button["reply"]["id"], button["reply"]["title"])
        for button in interactive["action"]["buttons"]
    ] == [
        (f"upc:alerts:pack:{order.pk}", "Mark packed"),
        (f"upc:alerts:ship:{order.pk}", "Mark shipped"),
        (f"upc:alerts:cancel:{order.pk}", "Cancel"),
    ]
    assert AlertMessage.objects.get().payload["mode"] == "free_form"


def test_an_expired_window_uses_the_template(recipient, order, fake_graph, fire):
    recipient.last_inbound_at = timezone.now() - timedelta(hours=25)
    recipient.save()

    fire(status_event(order, "pending_payment", "confirmed"))

    [sent] = fake_graph.sent_messages
    assert sent["type"] == "template"


def test_outside_window_error_falls_back_to_the_template_once(recipient, order, fake_graph, fire):
    recipient.last_inbound_at = timezone.now() - timedelta(hours=1)
    recipient.save()
    fake_graph.fail("send_message", OutsideWindowError("Re-engagement message", code=131047))

    fire(status_event(order, "pending_payment", "confirmed"))

    assert len(fake_graph.calls_to("send_message")) == 2
    [sent] = fake_graph.sent_messages
    assert sent["type"] == "template"
    message = AlertMessage.objects.get()
    assert message.status == AlertMessage.Status.SENT
    assert message.payload["fallback"] is True


def test_a_failed_fallback_is_logged(recipient, order, fake_graph, fire):
    recipient.last_inbound_at = timezone.now() - timedelta(hours=1)
    recipient.save()
    fake_graph.fail(
        "send_message", OutsideWindowError("Re-engagement message", code=131047), times=2
    )

    fire(status_event(order, "pending_payment", "confirmed"))

    assert len(fake_graph.calls_to("send_message")) == 2
    message = AlertMessage.objects.get()
    assert (message.status, message.error_code) == (AlertMessage.Status.FAILED, "131047")


def test_alerts_are_sent_once(recipient, order, fake_graph, fire):
    event = status_event(order, "pending_payment", "confirmed")

    fire(event)
    fire(event)
    result = tasks.send_alert.apply(
        args=[str(recipient.pk), str(order.pk), "new_order", "confirmed", "system"]
    ).get()

    assert result == "duplicate"
    assert len(fake_graph.sent_messages) == 1
    assert AlertMessage.objects.count() == 1


def test_only_verified_subscribed_recipients_in_the_workspace(
    workspace, other_workspace, store, order, fake_graph, fire
):
    subscribed = AlertRecipientFactory(workspace=workspace)
    AlertRecipientFactory(workspace=workspace, events=["needs_attention"])
    AlertRecipientFactory(workspace=workspace, status=AlertRecipient.Status.PENDING)
    AlertRecipientFactory(workspace=workspace, status=AlertRecipient.Status.OPTED_OUT)
    AlertRecipientFactory(workspace=other_workspace)

    fire(status_event(order, "pending_payment", "confirmed"))

    assert [sent["to"] for sent in fake_graph.sent_messages] == [subscribed.wa_id]


def test_nothing_is_sent_when_the_platform_is_unavailable(
    recipient, order, fake_graph, fire, settings
):
    settings.PLATFORM_WA_ACCESS_TOKEN = ""

    fire(status_event(order, "pending_payment", "confirmed"))

    assert fake_graph.sent_messages == []


def test_needs_attention_alert(recipient, order, fake_graph, fire):
    order.status = Order.Status.NEEDS_ATTENTION
    order.save()
    OrderEventFactory(
        order=order,
        type=OrderEvent.Type.STATUS_CHANGED,
        from_status="pending_payment",
        to_status="needs_attention",
        actor=OrderEvent.Actor.SYSTEM,
        detail="Payment arrived after the order expired",
    )

    fire(status_event(order, "pending_payment", "needs_attention"))

    [sent] = fake_graph.sent_messages
    assert sent["template"]["name"] == "upc_order_attention"
    assert template_params(sent) == [
        "Sharma Sweets",
        "SS-1001",
        "Payment arrived after the order expired",
    ]
    assert button_payloads(sent) == []
    assert AlertMessage.objects.get().kind == AlertMessage.Kind.NEEDS_ATTENTION


def test_buyer_cancellation_alert_is_text_inside_the_window(recipient, order, fake_graph, fire):
    recipient.last_inbound_at = timezone.now()
    recipient.save()
    order.status = Order.Status.CANCELLED
    order.cancel_reason = "Ordered by mistake"
    order.save()

    fire(status_event(order, "confirmed", "cancelled", actor="buyer"))

    [sent] = fake_graph.sent_messages
    assert sent["type"] == "text"
    assert "it was cancelled by the buyer (Ordered by mistake)" in body_of(sent)
    assert AlertMessage.objects.get().kind == AlertMessage.Kind.ORDER_CANCELLED


def test_a_retryable_failure_is_retried(recipient, order, fake_graph):
    fake_graph.fail("send_message", TransientError("Try later", code=131000))

    tasks.send_alert.apply(
        args=[str(recipient.pk), str(order.pk), "new_order", "confirmed", "system"], throw=False
    )

    assert len(fake_graph.calls_to("send_message")) == 2
    message = AlertMessage.objects.get()
    assert message.status == AlertMessage.Status.SENT


def test_cod_payment_label_and_long_item_summary(workspace, store):
    order = OrderFactory(
        workspace=workspace,
        payment_method=Order.PaymentMethod.COD,
        payment_status=Order.PaymentStatus.COD_PENDING,
    )
    for position in range(20):
        OrderItemFactory(order=order, name=f"Assorted sweets box {position}", position=position)

    outbound = content.new_order(order, "Sharma Sweets")

    summary = outbound.template_params[2]
    assert len(summary) <= 200
    assert summary.startswith("2 x Assorted sweets box 0, 2 x Assorted sweets box 1")
    assert summary.endswith("…")
    assert outbound.template_params[4] == "Cash on delivery"


@pytest.mark.parametrize(
    ("paise", "text"),
    [(0, "₹0.00"), (49800, "₹498.00"), (100000, "₹1,000.00"), (12345678, "₹1,23,456.78")],
)
def test_format_inr(paise, text):
    assert content.format_inr(paise) == text


def test_template_params_are_single_line():
    assert content.template_param("Line one\n\tline   two ") == "Line one line two"
    assert content.template_param("") == "—"
