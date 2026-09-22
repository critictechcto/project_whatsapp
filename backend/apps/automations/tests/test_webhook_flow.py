"""End to end: a signed Meta webhook with an inbound "PRICE" message gets an automation reply."""

import hashlib
import hmac
import json
import time

import pytest
from django.conf import settings
from django.urls import reverse

from apps.automations import tasks
from apps.automations.factories import AutomationRuleFactory
from apps.automations.models import AutomationRun
from apps.inbox.models import Message
from apps.whatsapp.factories import PhoneNumberFactory

pytestmark = pytest.mark.django_db

WABA_ID = "102290129340398"
PHONE_NUMBER_ID = "106540352242922"
CUSTOMER_WA_ID = "919876543210"
REPLY = "Our prices start at ₹499. Reply with a product name for details."


@pytest.fixture
def number(workspace):
    return PhoneNumberFactory(
        workspace=workspace,
        waba__workspace=workspace,
        waba__waba_id=WABA_ID,
        phone_number_id=PHONE_NUMBER_ID,
        display_phone_number="15550783881",
        is_default=True,
    )


@pytest.fixture
def deliver(client, django_capture_on_commit_callbacks):
    def _deliver(payload: dict) -> None:
        body = json.dumps(payload).encode()
        digest = hmac.new(settings.META_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("webhooks:meta-callback"),
                data=body,
                content_type="application/json",
                headers={"X-Hub-Signature-256": f"sha256={digest}"},
            )
        assert response.status_code == 200

    return _deliver


def inbound_text(text: str, wamid: str, timestamp: int, *, entry_time: int | None = None) -> dict:
    entry: dict = {
        "id": WABA_ID,
        "changes": [
            {
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15550783881",
                        "phone_number_id": PHONE_NUMBER_ID,
                    },
                    "contacts": [{"profile": {"name": "Priya Sharma"}, "wa_id": CUSTOMER_WA_ID}],
                    "messages": [
                        {
                            "from": CUSTOMER_WA_ID,
                            "id": wamid,
                            "timestamp": str(timestamp),
                            "type": "text",
                            "text": {"body": text},
                        }
                    ],
                },
            }
        ],
    }
    if entry_time is not None:
        entry["time"] = entry_time
    return {"object": "whatsapp_business_account", "entry": [entry]}


def test_price_keyword_webhook_queues_an_automation_reply(
    deliver, workspace, other_workspace, number, fake_graph, django_capture_on_commit_callbacks
):
    rule = AutomationRuleFactory(
        workspace=workspace,
        keywords=["price"],
        keyword_match="exact",
        phone_number=number,
        actions=[{"type": "send_text", "config": {"text": REPLY}}],
    )
    AutomationRuleFactory(workspace=other_workspace, keywords=["price"])
    now = int(time.time())

    deliver(inbound_text("PRICE", "wamid.PRICE1", now))
    deliver(inbound_text("PRICE", "wamid.PRICE1", now, entry_time=now + 1))  # Meta redelivery

    inbound = Message.objects.get(wamid="wamid.PRICE1")
    reply = Message.objects.get(source=Message.Source.AUTOMATION)
    assert reply.conversation_id == inbound.conversation_id
    assert reply.idempotency_key == f"automation:{rule.pk}:wamid.PRICE1:0"
    assert reply.source_ref == str(rule.pk)
    assert reply.text == REPLY
    # Queued, then dispatched on commit through the fake Graph client (Celery is eager).
    assert reply.status == Message.Status.SENT
    assert [(sent["to"], sent["text"]["body"]) for sent in fake_graph.sent_messages] == [
        (CUSTOMER_WA_ID, REPLY)
    ]
    run = AutomationRun.objects.get()
    assert (run.rule, run.message, run.status) == (rule, inbound, AutomationRun.Status.SUCCEEDED)

    # A re-emitted event for the same message changes nothing.
    with django_capture_on_commit_callbacks(execute=True):
        tasks.process_inbound.delay(str(inbound.pk), is_first_inbound=True)

    assert Message.objects.filter(source=Message.Source.AUTOMATION).count() == 1
    assert AutomationRun.objects.count() == 1
    assert len(fake_graph.sent_messages) == 1
    rule.refresh_from_db()
    assert rule.run_count == 1


def inbound_button_reply(reply_id: str, title: str, wamid: str, timestamp: int) -> dict:
    payload = inbound_text(title, wamid, timestamp)
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    del message["text"]
    message["type"] = "interactive"
    message["interactive"] = {
        "type": "button_reply",
        "button_reply": {"id": reply_id, "title": title},
    }
    return payload


def test_opt_in_buttons_record_consent_from_a_tap(deliver, workspace, number, fake_graph):
    rule = AutomationRuleFactory(
        workspace=workspace,
        keywords=["offers"],
        keyword_match="exact",
        phone_number=number,
        actions=[
            {
                "type": "send_opt_in_request",
                "config": {
                    "text": "Want new arrivals and offers on WhatsApp?",
                    "yes_label": "Yes, send offers",
                    "no_label": "No thanks",
                    "confirmation_text": "Subscribed ✅",
                    "decline_text": "",
                },
            }
        ],
    )
    now = int(time.time())

    deliver(inbound_text("OFFERS", "wamid.OFFERS1", now))

    request = fake_graph.sent_messages[-1]
    assert request["type"] == "interactive"
    buttons = request["interactive"]["action"]["buttons"]
    assert [button["reply"] for button in buttons] == [
        {"id": f"upc:consent:yes:{rule.pk}:0", "title": "Yes, send offers"},
        {"id": f"upc:consent:no:{rule.pk}:0", "title": "No thanks"},
    ]

    yes = buttons[0]["reply"]
    deliver(inbound_button_reply(yes["id"], yes["title"], "wamid.TAP1", now + 5))
    deliver(inbound_button_reply(yes["id"], yes["title"], "wamid.TAP1", now + 5))  # redelivery

    contact = Message.objects.get(wamid="wamid.TAP1").conversation.contact
    assert contact.marketing_opt_in_status == "opted_in"
    assert contact.opt_in_source == "whatsapp_button"
    assert list(contact.consent_events.values_list("source", "wamid")) == [
        ("whatsapp_button", "wamid.TAP1")
    ]
    replies = [sent for sent in fake_graph.sent_messages if sent.get("type") == "text"]
    assert [sent["text"]["body"] for sent in replies] == ["Subscribed ✅"]
    # The tap is answered by the consent handler only: no rule ran for it.
    assert AutomationRun.objects.count() == 1
