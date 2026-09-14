"""End to end: a signed inbound "PRICE" webhook becomes a conversation and a keyword reply."""

import time

import pytest

from apps.automations.factories import AutomationRuleFactory
from apps.automations.models import AutomationRun
from apps.contacts.models import Contact
from apps.inbox.models import Conversation, Message
from apps.webhooks.models import WebhookEvent

from .conftest import CUSTOMER_WA_ID, inbound_text

pytestmark = pytest.mark.django_db

REPLY = "Our prices start at ₹499."


def test_inbound_price_keyword_gets_one_automated_reply(
    deliver_meta, workspace, other_workspace, e2e_number, fake_graph
):
    rule = AutomationRuleFactory(
        workspace=workspace,
        keywords=["price"],
        actions=[{"type": "send_text", "config": {"text": REPLY}}],
    )
    now = int(time.time())
    payload = inbound_text("PRICE", "wamid.E2E.PRICE1", now)

    deliver_meta(payload)

    conversation = Conversation.objects.get(workspace=workspace)
    assert conversation.phone_number == e2e_number
    assert conversation.contact == Contact.objects.get(workspace=workspace, wa_id=CUSTOMER_WA_ID)
    inbound = Message.objects.get(wamid="wamid.E2E.PRICE1")
    assert (inbound.conversation, inbound.direction, inbound.text) == (
        conversation,
        Message.Direction.INBOUND,
        "PRICE",
    )
    assert inbound.status == Message.Status.RECEIVED

    reply = Message.objects.get(source=Message.Source.AUTOMATION)
    assert reply.conversation == conversation
    assert reply.idempotency_key == f"automation:{rule.pk}:wamid.E2E.PRICE1:0"
    assert reply.status == Message.Status.SENT
    assert [(sent["to"], sent["text"]["body"]) for sent in fake_graph.sent_messages] == [
        (CUSTOMER_WA_ID, REPLY)
    ]
    run = AutomationRun.objects.get()
    assert (run.rule, run.message, run.status) == (rule, inbound, AutomationRun.Status.SUCCEEDED)

    # Meta redelivers the same body, then the same message in a new envelope.
    deliver_meta(payload)
    deliver_meta(inbound_text("PRICE", "wamid.E2E.PRICE1", now, entry_time=now + 1))

    assert Conversation.objects.count() == 1
    assert Message.objects.filter(direction=Message.Direction.INBOUND).count() == 1
    assert Message.objects.filter(source=Message.Source.AUTOMATION).count() == 1
    assert AutomationRun.objects.count() == 1
    assert len(fake_graph.sent_messages) == 1
    assert set(WebhookEvent.objects.values_list("status", flat=True)) == {
        WebhookEvent.Status.PROCESSED
    }
    assert not Message.objects.filter(workspace=other_workspace).exists()
