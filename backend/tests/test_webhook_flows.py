"""End-to-end flows across apps: a signed Meta webhook reaches receivers in other apps."""

import hashlib
import hmac
import json

import pytest
from django.conf import settings
from django.urls import reverse

from apps.contacts.models import ConsentEvent, Contact
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.webhooks.models import WebhookEvent
from apps.whatsapp.factories import PhoneNumberFactory

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


def waba_payload(field: str, value: dict, *, entry_time: int | None = None) -> dict:
    entry: dict = {"id": WABA_ID, "changes": [{"field": field, "value": value}]}
    if entry_time is not None:
        entry["time"] = entry_time
    return {"object": "whatsapp_business_account", "entry": [entry]}


def messages_value(**value) -> dict:
    return {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550783881", "phone_number_id": PHONE_NUMBER_ID},
        **value,
    }


def inbound_text(text: str, wamid: str, *, entry_time: int | None = None) -> dict:
    value = messages_value(
        contacts=[{"profile": {"name": "Priya Sharma"}, "wa_id": CUSTOMER_WA_ID}],
        messages=[
            {
                "from": CUSTOMER_WA_ID,
                "id": wamid,
                "timestamp": "1757830000",
                "type": "text",
                "text": {"body": text},
            }
        ],
    )
    return waba_payload("messages", value, entry_time=entry_time)


def test_stop_and_start_keywords_update_consent_once_per_message(
    deliver, workspace, other_workspace, number
):
    stop = inbound_text("STOP", "wamid.STOP1")
    deliver(stop)
    deliver(stop)  # identical redelivery is deduplicated by body hash
    deliver(inbound_text("STOP", "wamid.STOP1", entry_time=1757830001))  # same message, new body

    contact = Contact.objects.get(workspace=workspace, phone_e164="+919876543210")
    assert contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT
    assert contact.name == "Priya Sharma"
    assert contact.last_inbound_at is not None
    assert WebhookEvent.objects.count() == 2
    assert set(WebhookEvent.objects.values_list("status", flat=True)) == {
        WebhookEvent.Status.PROCESSED
    }
    events = ConsentEvent.objects.filter(contact=contact)
    assert [(e.action, e.source) for e in events] == [
        (ConsentEvent.Action.OPT_OUT, ConsentEvent.Source.WHATSAPP_KEYWORD)
    ]

    deliver(inbound_text("start", "wamid.START1"))

    contact.refresh_from_db()
    assert contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_IN
    assert ConsentEvent.objects.filter(contact=contact).count() == 2
    assert not Contact.objects.filter(workspace=other_workspace).exists()


def test_marketing_opt_out_error_on_status_opts_contact_out(deliver, workspace, number):
    value = messages_value(
        statuses=[
            {
                "id": "wamid.FAILED1",
                "status": "failed",
                "timestamp": "1757830600",
                "recipient_id": "919812345678",
                "errors": [
                    {
                        "code": 131050,
                        "title": "Unable to deliver the message.",
                        "message": "Unable to deliver the message.",
                        "error_data": {"details": "The recipient stopped marketing messages."},
                    }
                ],
            }
        ]
    )

    deliver(waba_payload("messages", value))

    contact = Contact.objects.get(workspace=workspace, phone_e164="+919812345678")
    assert contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT
    assert contact.consent_events.get().source == ConsentEvent.Source.META_MARKETING_OPTOUT


def test_template_status_webhooks_update_template(deliver, number):
    template = MessageTemplateFactory(
        waba=number.waba,
        meta_template_id="1689556908129832",
        name="diwali_offer_2026",
        language="en_US",
        status=MessageTemplate.Status.PENDING,
    )

    def status_update(event: str, reason: str) -> dict:
        return waba_payload(
            "message_template_status_update",
            {
                "event": event,
                "message_template_id": 1689556908129832,
                "message_template_name": "diwali_offer_2026",
                "message_template_language": "en_US",
                "reason": reason,
            },
        )

    deliver(status_update("APPROVED", "NONE"))
    template.refresh_from_db()
    assert template.status == MessageTemplate.Status.APPROVED
    assert template.rejected_reason == ""

    deliver(status_update("REJECTED", "INVALID_FORMAT"))
    template.refresh_from_db()
    assert template.status == MessageTemplate.Status.REJECTED
    assert template.rejected_reason
