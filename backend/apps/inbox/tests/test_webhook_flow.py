"""End to end: a signed Meta webhook becomes a conversation, a reply is sent and delivery
statuses arrive through the webhook again."""

import hashlib
import hmac
import json
import time

import pytest
from django.conf import settings
from django.urls import reverse

from apps.inbox import sending
from apps.inbox.models import Conversation, Message
from apps.webhooks.models import WebhookEvent
from apps.whatsapp.factories import PhoneNumberFactory
from common.events import MessageDeliveryUpdated, MessageRecorded

pytestmark = pytest.mark.django_db

WABA_ID = "102290129340398"
PHONE_NUMBER_ID = "106540352242922"
CUSTOMER_WA_ID = "919876543210"


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


def messages_payload(*, entry_time: int | None = None, **value) -> dict:
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
                    **value,
                },
            }
        ],
    }
    if entry_time is not None:
        entry["time"] = entry_time
    return {"object": "whatsapp_business_account", "entry": [entry]}


def inbound_text(text: str, wamid: str, timestamp: int, *, entry_time: int | None = None) -> dict:
    return messages_payload(
        entry_time=entry_time,
        contacts=[{"profile": {"name": "Priya Sharma"}, "wa_id": CUSTOMER_WA_ID}],
        messages=[
            {
                "from": CUSTOMER_WA_ID,
                "id": wamid,
                "timestamp": str(timestamp),
                "type": "text",
                "text": {"body": text},
            }
        ],
    )


def status_update(wamid: str, value: str, timestamp: int) -> dict:
    return messages_payload(
        statuses=[
            {
                "id": wamid,
                "status": value,
                "timestamp": str(timestamp),
                "recipient_id": CUSTOMER_WA_ID,
                "pricing": {"billable": False, "pricing_model": "PMP", "category": "service"},
            }
        ]
    )


def test_inbound_webhook_reply_and_delivery_statuses(
    deliver,
    workspace,
    other_workspace,
    number,
    fake_graph,
    django_capture_on_commit_callbacks,
    recorded,
):
    now = int(time.time())
    question = inbound_text("Is my order shipped?", "wamid.IN1", now)

    deliver(question)
    deliver(question)  # identical redelivery: deduplicated by body hash
    deliver(inbound_text("Is my order shipped?", "wamid.IN1", now, entry_time=now + 1))

    conversation = Conversation.objects.get(workspace=workspace)
    assert conversation.phone_number == number
    assert conversation.contact.name == "Priya Sharma"
    assert conversation.unread_count == 1
    inbound = conversation.messages.get()
    assert (inbound.direction, inbound.text) == ("inbound", "Is my order shipped?")
    assert sending.window_open(conversation.contact, number)
    assert len(recorded.of(MessageRecorded)) == 1
    assert set(WebhookEvent.objects.values_list("status", flat=True)) == {
        WebhookEvent.Status.PROCESSED
    }

    with django_capture_on_commit_callbacks(execute=True):
        reply = sending.send_message(
            workspace=workspace,
            contact=conversation.contact,
            content=sending.TextContent("Yes, it shipped today."),
            conversation=conversation,
            reply_to_wamid=inbound.wamid,
            source=Message.Source.INBOX,
            idempotency_key="inbox:reply-1",
        )
    reply.refresh_from_db()
    assert reply.status == Message.Status.SENT
    assert fake_graph.sent_messages[0]["to"] == CUSTOMER_WA_ID

    deliver(status_update(reply.wamid, "delivered", now + 5))
    deliver(status_update(reply.wamid, "read", now + 9))
    deliver(status_update(reply.wamid, "delivered", now + 5))  # late duplicate

    reply.refresh_from_db()
    assert reply.status == Message.Status.READ
    assert reply.pricing_category == "service"
    assert reply.billable is False
    assert [e.status for e in recorded.of(MessageDeliveryUpdated)] == ["sent", "delivered", "read"]
    assert not Conversation.objects.filter(workspace=other_workspace).exists()
    assert not Message.objects.filter(workspace=other_workspace).exists()
