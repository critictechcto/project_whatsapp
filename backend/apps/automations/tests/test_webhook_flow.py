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
