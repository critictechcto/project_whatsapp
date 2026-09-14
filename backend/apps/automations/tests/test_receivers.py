from types import SimpleNamespace

import pytest

from apps.automations import receivers
from apps.automations.factories import AutomationRuleFactory
from apps.automations.models import AutomationRun
from apps.inbox import services as inbox_services
from apps.inbox.factories import MessageFactory
from apps.inbox.models import Message

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
