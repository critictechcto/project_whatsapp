from types import SimpleNamespace

import pytest

from apps.automations import receivers
from apps.automations.factories import AutomationRuleFactory
from apps.automations.models import AutomationRun
from apps.inbox import services as inbox_services
from apps.inbox.factories import MessageFactory
from apps.inbox.models import Message
from common import commerce

pytestmark = pytest.mark.django_db


@pytest.fixture
def enqueued(monkeypatch):
    calls: list[tuple] = []
    fake_task = SimpleNamespace(delay=lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(receivers, "process_inbound", fake_task)
    return calls


def test_inbound_message_enqueues_processing_after_commit(conversation, inbound, commit, enqueued):
    message = inbound("hi")

    with commit():
        inbox_services.emit_message_recorded(
            message, conversation, is_first_inbound=True, contact_created=True
        )
        assert enqueued == []

    assert enqueued == [((str(message.pk),), {"is_first_inbound": True, "contact_created": True})]


def test_carts_are_claimed_by_commerce(conversation, inbound, commit, enqueued):
    message = inbound("Cart: 2 items, ₹1,300.00", type=Message.Type.ORDER)

    with commit():
        inbox_services.emit_message_recorded(message, conversation, is_first_inbound=True)

    assert enqueued == []


@pytest.mark.parametrize("reply_id", ["upc:shop:menu", "upc:nfm:address_message"])
def test_commerce_replies_are_claimed(conversation, inbound, commit, enqueued, reply_id):
    message = inbound("Browse", type=Message.Type.INTERACTIVE)

    with commit():
        inbox_services.emit_message_recorded(message, conversation, reply_id=reply_id)

    assert enqueued == []


def test_other_replies_still_reach_automations(conversation, inbound, commit, enqueued):
    message = inbound("Track order", type=Message.Type.BUTTON)

    with commit():
        inbox_services.emit_message_recorded(message, conversation, reply_id="track-order")

    assert len(enqueued) == 1


def test_registered_claimers_skip_automations_without_a_run(
    workspace, conversation, inbound, commit, enqueued
):
    AutomationRuleFactory(workspace=workspace, keywords=["menu"])

    def claim_menu(event):
        return event.text.strip().lower() == "menu"

    commerce.register_message_claimer(claim_menu)
    try:
        with commit():
            inbox_services.emit_message_recorded(inbound("MENU"), conversation)
            inbox_services.emit_message_recorded(inbound("price"), conversation)
    finally:
        commerce.unregister_message_claimer(claim_menu)

    assert [args for args, _ in enqueued] == [(str(Message.objects.get(text="price").pk),)]
    assert not AutomationRun.objects.exists()


@pytest.mark.parametrize("source", ["inbox", "campaign", "automation", "api"])
def test_outbound_messages_are_ignored(conversation, commit, enqueued, source):
    message = MessageFactory(conversation=conversation, source=source)

    with commit():
        inbox_services.emit_message_recorded(message, conversation)

    assert enqueued == []


def test_automation_replies_do_not_trigger_more_automations(
    workspace, conversation, inbound, commit, fake_graph
):
    # The reply itself contains the keyword: a loop would answer it again.
    rule = AutomationRuleFactory(
        workspace=workspace,
        keywords=["price"],
        keyword_match="contains",
        actions=[{"type": "send_text", "config": {"text": "The price is ₹499."}}],
    )
    message = inbound("price?")

    with commit():
        inbox_services.emit_message_recorded(message, conversation, is_first_inbound=True)

    reply = Message.objects.get(source=Message.Source.AUTOMATION)
    assert reply.status == Message.Status.SENT
    assert len(fake_graph.sent_messages) == 1
    assert AutomationRun.objects.get().rule == rule
