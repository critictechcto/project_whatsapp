"""Claiming, the MessageRecorded wiring and cart clean-up after a confirmed order."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.automations.factories import AutomationRuleFactory
from apps.automations.models import AutomationRun
from apps.billing import services as billing_services
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Message
from apps.orders.models import Order
from apps.shop.claims import claim_shop_message
from apps.shop.content import shop_id
from apps.shop.factories import BotSessionFactory
from apps.shop.models import BotSession
from apps.whatsapp.factories import PhoneNumberFactory
from common import events
from common.commerce import is_claimed_by_commerce

from .helpers import button_ids, recorded_event


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


def inbound(conversation, text="hi", **kwargs):
    return MessageFactory(conversation=conversation, inbound=True, text=text, **kwargs)


# --- Claiming -----------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["hi", "  HELLO ", "Menu", "shop", "start"])
def test_menu_keywords_are_claimed_while_the_store_is_enabled(store, conversation, text):
    event = recorded_event(inbound(conversation, text))

    assert claim_shop_message(event) is True
    assert is_claimed_by_commerce(event) is True


def test_keywords_are_not_claimed_when_the_store_is_disabled(store, conversation):
    store.enabled = False
    store.save()
    event = recorded_event(inbound(conversation, "hi"))

    assert claim_shop_message(event) is False
    assert is_claimed_by_commerce(event) is False


def test_nothing_is_claimed_without_store_settings(conversation):
    assert claim_shop_message(recorded_event(inbound(conversation, "hi"))) is False


def test_keywords_are_not_claimed_without_the_commerce_feature(store, workspace, conversation):
    subscription = billing_services.get_subscription(workspace)
    subscription.status = "cancelled"
    subscription.save()

    assert claim_shop_message(recorded_event(inbound(conversation, "hi"))) is False


@pytest.mark.parametrize("text", ["hi there", "price", "", "hi!"])
def test_other_text_is_not_claimed(store, conversation, text):
    assert claim_shop_message(recorded_event(inbound(conversation, text))) is False


def test_keywords_on_another_number_are_not_claimed(store, workspace, contact):
    other = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)
    conversation = ConversationFactory(workspace=workspace, contact=contact, phone_number=other)

    assert claim_shop_message(recorded_event(inbound(conversation, "hi"))) is False


def test_non_text_messages_are_not_claimed_by_the_shop(store, conversation):
    message = inbound(conversation, "hi", type=Message.Type.BUTTON)

    assert claim_shop_message(recorded_event(message)) is False


def test_outbound_messages_are_not_claimed(store, conversation):
    message = MessageFactory(conversation=conversation, text="hi")

    assert claim_shop_message(recorded_event(message)) is False


def test_typed_quantities_are_claimed_only_while_awaited(store, conversation):
    event = recorded_event(inbound(conversation, "3"))
    assert claim_shop_message(event) is False

    session = BotSessionFactory(conversation=conversation, state=BotSession.State.AWAITING_QUANTITY)
    assert claim_shop_message(event) is True

    session.expires_at = timezone.now() - timedelta(minutes=1)
    session.save()
    assert claim_shop_message(event) is False


# --- MessageRecorded wiring ---------------------------------------------------------------------


def test_keyword_gets_the_menu_and_skips_automations(store, workspace, conversation, commit):
    AutomationRuleFactory(workspace=workspace, keywords=["hi"])
    message = inbound(conversation, "hi")

    with commit():
        events.emit(events.message_recorded, recorded_event(message))

    outbound = list(Message.objects.filter(direction=Message.Direction.OUTBOUND))
    assert len(outbound) == 1
    assert outbound[0].source_ref == "shop"
    assert button_ids(outbound[0])[0] == shop_id("browse")
    assert not AutomationRun.objects.exists()


def test_redelivered_events_are_answered_once(store, conversation, commit):
    message = inbound(conversation, "menu")
    event = recorded_event(message)

    for _ in range(2):
        with commit():
            events.emit(events.message_recorded, event)

    assert Message.objects.filter(direction=Message.Direction.OUTBOUND).count() == 1


def test_reply_id_from_the_event_is_used(store, conversation, product, commit, orders_calls):
    reply_id = shop_id("add", product.pk, 2)
    message = inbound(conversation, "Add to cart", type=Message.Type.INTERACTIVE, payload={})

    with commit():
        events.emit(events.message_recorded, recorded_event(message, reply_id=reply_id))

    assert BotSession.objects.get(conversation=conversation).cart == [
        {"product_id": str(product.pk), "quantity": 2}
    ]


def test_no_task_without_an_enabled_store(conversation, commit, monkeypatch):
    from apps.shop import tasks

    calls = []
    monkeypatch.setattr(tasks.handle_inbound, "delay", lambda *args: calls.append(args))

    with commit():
        events.emit(events.message_recorded, recorded_event(inbound(conversation, "hi")))

    assert calls == []


# --- Orders -------------------------------------------------------------------------------------


def status_event(conversation, old_status, new_status):
    return events.OrderStatusChanged(
        workspace_id=conversation.workspace_id,
        order_id=uuid.uuid4(),
        order_number="SS-1001",
        contact_id=conversation.contact_id,
        phone_number_id=conversation.phone_number_id,
        old_status=old_status,
        new_status=new_status,
        payment_status="paid",
        payment_method="online",
        total_paise=49900,
        actor="system",
        actor_user_id=None,
        occurred_at=timezone.now(),
    )


CART = [{"product_id": "0b7f6f7e-4a57-4b3e-9a4a-4b0d1f3f7c11", "quantity": 1}]


def test_confirmed_order_clears_the_bot_cart(conversation):
    session = BotSessionFactory(conversation=conversation, cart=CART)

    events.emit(
        events.order_status_changed,
        status_event(conversation, Order.Status.PENDING_PAYMENT, Order.Status.CONFIRMED),
    )

    session.refresh_from_db()
    assert session.cart == []


@pytest.mark.parametrize(
    ("old_status", "new_status"),
    [
        (Order.Status.CONFIRMED, Order.Status.PACKED),
        (Order.Status.NEEDS_ATTENTION, Order.Status.CONFIRMED),
        (Order.Status.AWAITING_ADDRESS, Order.Status.CANCELLED),
    ],
)
def test_other_status_changes_keep_the_cart(conversation, old_status, new_status):
    session = BotSessionFactory(conversation=conversation, cart=CART)

    events.emit(events.order_status_changed, status_event(conversation, old_status, new_status))

    session.refresh_from_db()
    assert session.cart == CART
