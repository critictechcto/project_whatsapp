"""End to end: launch a campaign, receive signed delivery statuses and a reply through Meta
webhooks, and watch recipient states and campaign stats follow."""

import time

import pytest

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.contacts.factories import ContactFactory, TagFactory
from apps.contacts.models import Contact
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate

from .conftest import inbound_text, status_update

pytestmark = pytest.mark.django_db

CAMPAIGNS = "/api/v1/campaigns/"
MAPPING = {
    "body": [
        {"source": "contact_field", "value": "name", "fallback": "there"},
        {"source": "static", "value": "ORD-1001", "fallback": ""},
    ],
    "header": None,
    "buttons": {},
}
UNDELIVERABLE = 131026


def test_campaign_lifecycle_through_meta_webhooks(
    auth_client, deliver_meta, workspace, e2e_number, fake_graph, django_capture_on_commit_callbacks
):
    template = MessageTemplateFactory(
        waba=e2e_number.waba,
        status=MessageTemplate.Status.APPROVED,
        category=MessageTemplate.Category.MARKETING,
    )
    tag = TagFactory(workspace=workspace)
    reader, receiver, unreachable = (
        ContactFactory(
            workspace=workspace, marketing_opt_in_status=Contact.OptInStatus.OPTED_IN, tags=[tag]
        )
        for _ in range(3)
    )
    opted_out = ContactFactory(
        workspace=workspace, marketing_opt_in_status=Contact.OptInStatus.OPTED_OUT, tags=[tag]
    )
    client = auth_client()

    created = client.post(
        CAMPAIGNS,
        {
            "name": "Diwali sale",
            "template_id": str(template.pk),
            "audience": {"tag_ids": [str(tag.pk)], "match": "any", "contact_ids": []},
            "variable_mapping": MAPPING,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    campaign_url = f"{CAMPAIGNS}{created.json()['id']}/"

    with django_capture_on_commit_callbacks(execute=True):
        launched = client.post(f"{campaign_url}launch/", {"consent_attested": True}, format="json")

    assert launched.status_code == 200, launched.content
    campaign = Campaign.objects.get(pk=created.json()["id"])
    recipients = {
        recipient.contact_id: recipient
        for recipient in CampaignRecipient.objects.filter(campaign=campaign).select_related(
            "message"
        )
    }
    assert recipients[opted_out.pk].status == CampaignRecipient.Status.SKIPPED
    assert sorted(sent["to"] for sent in fake_graph.sent_messages) == sorted(
        contact.wa_id for contact in (reader, receiver, unreachable)
    )
    assert all(
        sent["type"] == "template" and sent["template"]["name"] == template.name
        for sent in fake_graph.sent_messages
    )

    def wamid(contact):
        return recipients[contact.pk].message.wamid

    now = int(time.time()) - 60
    for status, offset in (("sent", 1), ("delivered", 2), ("read", 3)):
        deliver_meta(status_update(wamid(reader), status, now + offset, wa_id=reader.wa_id))
    for status, offset in (("sent", 1), ("delivered", 2)):
        deliver_meta(status_update(wamid(receiver), status, now + offset, wa_id=receiver.wa_id))
    deliver_meta(
        status_update(
            wamid(unreachable), "failed", now + 2, wa_id=unreachable.wa_id, error_code=UNDELIVERABLE
        )
    )
    # A late duplicate never moves a recipient backwards.
    deliver_meta(status_update(wamid(reader), "delivered", now + 2, wa_id=reader.wa_id))

    def statuses():
        return {
            contact_id: status
            for contact_id, status in CampaignRecipient.objects.filter(
                campaign=campaign
            ).values_list("contact_id", "status")
        }

    assert statuses() == {
        reader.pk: CampaignRecipient.Status.READ,
        receiver.pk: CampaignRecipient.Status.DELIVERED,
        unreachable.pk: CampaignRecipient.Status.FAILED,
        opted_out.pk: CampaignRecipient.Status.SKIPPED,
    }
    failed = CampaignRecipient.objects.get(campaign=campaign, contact=unreachable)
    assert failed.error_code == str(UNDELIVERABLE)

    body = client.get(campaign_url).json()
    assert body["status"] == "completed"
    assert body["stats"] == {
        "total": 4,
        "skipped": 1,
        "queued": 0,
        "sent": 2,
        "delivered": 2,
        "read": 1,
        "failed": 1,
        "replied": 0,
    }

    reply = inbound_text(
        "Is the sale on tomorrow?",
        "wamid.E2E.REPLY1",
        int(time.time()) + 2,
        wa_id=reader.wa_id,
        name=reader.name or "Reader",
    )
    deliver_meta(reply)
    deliver_meta(reply)  # redelivery counts once

    assert client.get(campaign_url).json()["stats"]["replied"] == 1
    assert CampaignRecipient.objects.get(campaign=campaign, contact=reader).replied_at is not None
