"""Buyer status notifications: session message inside the window, mapped template outside it."""

import pytest

from apps.contacts.factories import ContactFactory
from apps.inbox.factories import ConversationFactory
from apps.inbox.models import Message
from apps.message_templates.factories import MessageTemplateFactory, standard_components
from apps.message_templates.models import MessageTemplate
from apps.orders import notifications
from apps.orders.factories import OrderFactory, StoreSettingsFactory
from apps.orders.models import OrderEvent

pytestmark = pytest.mark.django_db

SHIPPED_BODY = "Hi {{1}}, order {{2}} shipped with {{3}}, AWB {{4}}, track at {{5}} today."


def shipped_order(workspace, number, **fields):
    contact = ContactFactory(workspace=workspace, name="Asha Verma")
    ConversationFactory(workspace=workspace, contact=contact, phone_number=number)
    return OrderFactory(
        workspace=workspace,
        contact=contact,
        phone_number=number,
        status="shipped",
        courier_name="Delhivery",
        awb_number="DL1",
        **fields,
    )


def test_inside_the_window_a_session_message_is_sent(workspace, number):
    conversation = ConversationFactory(workspace=workspace, phone_number=number, window_open=True)
    order = OrderFactory(
        workspace=workspace,
        contact=conversation.contact,
        phone_number=number,
        conversation=conversation,
    )

    message = notifications.notify_buyer(order, "confirmed", actor="system")

    assert message.type == Message.Type.INTERACTIVE
    assert order.number in message.text
    event = order.events.get(type=OrderEvent.Type.NOTIFICATION_SENT)
    assert event.message_id == message.pk
    assert event.metadata == {"notification": "confirmed"}


def test_outside_the_window_the_mapped_template_is_sent(workspace, number):
    template = MessageTemplateFactory(
        waba=number.waba,
        name="upc_order_shipped",
        status=MessageTemplate.Status.APPROVED,
        components=standard_components(SHIPPED_BODY),
    )
    StoreSettingsFactory(workspace=workspace, shipped_template=template)
    order = shipped_order(workspace, number)

    message = notifications.notify_buyer(order, "shipped", actor="dashboard")

    assert message.type == Message.Type.TEMPLATE
    assert message.template_id == template.pk
    assert "Delhivery" in message.text
    assert order.events.get(type=OrderEvent.Type.NOTIFICATION_SENT).message_id == message.pk


def test_outside_the_window_without_a_template_the_notification_fails(workspace, number):
    order = shipped_order(workspace, number)

    assert notifications.notify_buyer(order, "shipped", actor="dashboard") is None

    event = order.events.get()
    assert event.type == OrderEvent.Type.NOTIFICATION_FAILED
    assert "no template" in event.detail
    assert not Message.objects.exists()


def test_an_unapproved_template_is_not_sent(workspace, number):
    template = MessageTemplateFactory(
        waba=number.waba,
        status=MessageTemplate.Status.PENDING,
        components=standard_components(SHIPPED_BODY),
    )
    StoreSettingsFactory(workspace=workspace, shipped_template=template)
    order = shipped_order(workspace, number)

    assert notifications.notify_buyer(order, "shipped", actor="dashboard") is None

    assert order.events.get().type == OrderEvent.Type.NOTIFICATION_FAILED
    assert not Message.objects.exists()


def test_template_params_follow_the_contract(workspace):
    contact = ContactFactory(workspace=workspace, name="Asha")
    order = OrderFactory(
        workspace=workspace,
        contact=contact,
        total_paise=145000,
        payment_method="cod",
        payment_status="cod_pending",
    )

    assert notifications.template_params(order, "confirmed") == [
        "Asha",
        order.number,
        "₹1,450.00",
        "Cash on delivery",
    ]
    assert notifications.template_params(order, "packed") == ["Asha", order.number]
    assert notifications.template_params(order, "shipped") == ["Asha", order.number, "—", "—", "—"]
    assert notifications.template_params(order, "cancelled") == ["Asha", order.number, "—"]
    assert notifications.template_params(
        order, "payment_reminder", payment_url="https://rzp.io/i/x"
    ) == ["Asha", order.number, "₹1,450.00", "https://rzp.io/i/x"]
