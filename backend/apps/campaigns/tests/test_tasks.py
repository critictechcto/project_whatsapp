from datetime import timedelta

import pytest
from django.utils import timezone

from apps.campaigns import services, tasks
from apps.campaigns.models import Campaign, CampaignRecipient
from apps.contacts.models import Contact
from apps.inbox import sending
from apps.inbox.models import Message
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.models import PhoneNumber

pytestmark = pytest.mark.django_db


def statuses(campaign) -> list[str]:
    return list(
        CampaignRecipient.objects.filter(campaign=campaign)
        .order_by("created_at", "pk")
        .values_list("status", flat=True)
    )


def test_send_batch_queues_one_message_per_recipient(launched, fake_graph):
    campaign, _ = launched(3)

    result = tasks.send_batch.apply(args=[str(campaign.pk)])

    assert result.get() == 3
    recipients = CampaignRecipient.objects.filter(campaign=campaign).select_related("message")
    for recipient in recipients:
        message = recipient.message
        assert recipient.status == "queued"
        assert recipient.queued_at is not None
        assert message.source == Message.Source.CAMPAIGN
        assert message.source_ref == str(campaign.pk)
        assert message.idempotency_key == f"campaign:{campaign.pk}:recipient:{recipient.pk}"
        assert message.status == Message.Status.QUEUED
        assert message.text == f"Hi {recipient.contact.name}, your order ORD-1001 has shipped."
    campaign.refresh_from_db()
    assert campaign.stats["queued"] == 3
    assert fake_graph.calls_to("send_message") == []  # dispatch happens on commit


def test_duplicate_batches_never_send_twice(launched):
    campaign, _ = launched(2)

    assert tasks.send_batch.apply(args=[str(campaign.pk)]).get() == 2
    assert tasks.send_batch.apply(args=[str(campaign.pk)]).get() == 0
    assert Message.objects.count() == 2

    # A batch that crashed after creating messages but before saving recipients re-runs safely.
    messages = set(Message.objects.values_list("pk", flat=True))
    CampaignRecipient.objects.filter(campaign=campaign).update(status="pending", message=None)
    Campaign.objects.filter(pk=campaign.pk).update(queued_count=0)

    assert tasks.send_batch.apply(args=[str(campaign.pk)]).get() == 2
    assert set(Message.objects.values_list("pk", flat=True)) == messages
    assert (
        set(
            CampaignRecipient.objects.filter(campaign=campaign).values_list("message_id", flat=True)
        )
        == messages
    )


def test_full_run_in_batches(launched, commit, fake_graph, settings):
    settings.CAMPAIGN_BATCH_SIZE = 2
    campaign, _ = launched(5)

    with commit():
        tasks.send_batch.apply(args=[str(campaign.pk)])

    assert len(fake_graph.calls_to("send_message")) == 5
    assert statuses(campaign) == ["sent"] * 5
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.COMPLETED
    assert campaign.completed_at is not None
    assert campaign.stats == {
        "total": 5,
        "skipped": 0,
        "queued": 0,
        "sent": 5,
        "delivered": 0,
        "read": 0,
        "failed": 0,
        "replied": 0,
    }


def test_pause_stops_batches_and_resume_finishes(launched, commit, fake_graph, settings):
    settings.CAMPAIGN_BATCH_SIZE = 2
    campaign, _ = launched(5)
    tasks.send_batch.apply(args=[str(campaign.pk)])
    first = list(Message.objects.values_list("pk", flat=True))

    services.pause(campaign)
    assert tasks.send_batch.apply(args=[str(campaign.pk)]).get() == 0
    assert statuses(campaign).count("pending") == 3

    with commit():
        services.resume(campaign)
        sending.enqueue(first)

    assert len(fake_graph.calls_to("send_message")) == 5
    assert Message.objects.count() == 5
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.COMPLETED


def test_cancelled_campaign_sends_nothing(launched, fake_graph):
    campaign, _ = launched(2)
    services.cancel(campaign)

    assert tasks.send_batch.apply(args=[str(campaign.pk)]).get() == 0
    assert not Message.objects.exists()


def test_consent_is_rechecked_before_sending(launched):
    campaign, contacts = launched(3)
    Contact.objects.filter(pk=contacts[0].pk).update(
        marketing_opt_in_status=Contact.OptInStatus.OPTED_OUT
    )
    Contact.objects.filter(pk=contacts[1].pk).update(
        marketing_opt_in_status=Contact.OptInStatus.UNKNOWN
    )

    tasks.send_batch.apply(args=[str(campaign.pk)])

    rows = dict(
        CampaignRecipient.objects.filter(campaign=campaign).values_list("contact_id", "skip_reason")
    )
    assert rows == {contacts[0].pk: "opted_out", contacts[1].pk: "not_opted_in", contacts[2].pk: ""}
    assert Message.objects.count() == 1
    campaign.refresh_from_db()
    assert campaign.stats["skipped"] == 2
    assert campaign.stats["queued"] == 1


def test_batch_pauses_when_template_is_no_longer_approved(launched, template):
    campaign, _ = launched(2)
    MessageTemplate.objects.filter(pk=template.pk).update(status=MessageTemplate.Status.PAUSED)

    tasks.send_batch.apply(args=[str(campaign.pk)])

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.PAUSED
    assert "no longer approved" in campaign.last_error
    assert statuses(campaign) == ["pending", "pending"]
    assert not Message.objects.exists()


def test_batch_pauses_when_number_is_not_registered(launched, number):
    campaign, _ = launched(1)
    PhoneNumber.objects.filter(pk=number.pk).update(
        registration_status=PhoneNumber.RegistrationStatus.DEREGISTERED
    )

    tasks.send_batch.apply(args=[str(campaign.pk)])

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.PAUSED
    assert campaign.last_error
    assert statuses(campaign) == ["pending"]


def test_recipient_params_are_resolved_at_launch(number, template, tag, make_contact):
    from apps.campaigns.factories import CampaignFactory

    from .conftest import tag_audience

    make_contact(name="", attributes={"order": "A-17"})
    make_contact(attributes={})
    mapping = {
        "body": [
            {"source": "contact_field", "value": "name", "fallback": "there"},
            {"source": "attribute", "value": "order", "fallback": ""},
        ],
        "header": None,
        "buttons": {},
    }
    campaign = CampaignFactory(
        phone_number=number, template=template, audience=tag_audience(tag), variable_mapping=mapping
    )

    services.launch(campaign, actor=None)
    tasks.send_batch.apply(args=[str(campaign.pk)])

    sent = CampaignRecipient.objects.get(campaign=campaign, status="queued")
    assert sent.params == {"body": ["there", "A-17"], "header": None, "buttons": {}}
    assert Message.objects.get().text == "Hi there, your order A-17 has shipped."
    skipped = CampaignRecipient.objects.get(campaign=campaign, status="skipped")
    assert skipped.skip_reason == "missing_variable"


def test_start_due_starts_scheduled_campaigns(launched, commit, fake_graph):
    campaign, _ = launched(1, scheduled_at=timezone.now() + timedelta(hours=1))

    assert tasks.start_due.apply().get() == 0
    Campaign.objects.filter(pk=campaign.pk).update(
        scheduled_at=timezone.now() - timedelta(minutes=1)
    )
    with commit():
        assert tasks.start_due.apply().get() == 1

    campaign.refresh_from_db()
    assert campaign.started_at is not None
    assert campaign.status == Campaign.Status.COMPLETED
    assert len(fake_graph.calls_to("send_message")) == 1


def test_start_due_restarts_a_lost_batch_chain(launched, commit, fake_graph):
    campaign, _ = launched(2)  # the launch's batch was never scheduled

    with commit():
        tasks.start_due.apply()

    assert len(fake_graph.calls_to("send_message")) == 2
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.COMPLETED


def test_beat_schedule():
    from apps.campaigns.schedules import BEAT_SCHEDULE

    assert BEAT_SCHEDULE["campaigns.start_due"]["task"] == tasks.start_due.name
