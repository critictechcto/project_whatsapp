import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.campaigns import services
from apps.campaigns.factories import CampaignFactory
from apps.campaigns.models import Campaign, CampaignRecipient
from common import events, realtime

pytestmark = pytest.mark.django_db


def delivery(recipient, status, *, error_code="", at=None, source="campaign"):
    message = recipient.message
    return events.MessageDeliveryUpdated(
        workspace_id=message.workspace_id,
        message_id=message.pk,
        conversation_id=message.conversation_id,
        source=source,
        source_ref=str(recipient.campaign_id),
        status=status,
        error_code=error_code,
        occurred_at=at or timezone.now(),
    )


def inbound(recipient, *, at=None, direction="inbound"):
    campaign = recipient.campaign
    return events.MessageRecorded(
        workspace_id=campaign.workspace_id,
        message_id=uuid.uuid4(),
        conversation_id=recipient.message.conversation_id,
        contact_id=recipient.contact_id,
        phone_number_id=campaign.phone_number_id,
        direction=direction,
        source="inbound",
        source_ref="",
        type="text",
        text="Yes please",
        reply_id=None,
        wamid=f"wamid.{uuid.uuid4().hex}",
        is_first_inbound=False,
        contact_created=False,
        created_at=at or timezone.now(),
    )


def reload(instance):
    instance.refresh_from_db()
    return instance


# --- Delivery statuses ----------------------------------------------------------------------------


def test_out_of_order_statuses_only_move_forward(queued, emit):
    campaign, (first, _) = queued(2)

    emit(events.message_delivery_updated, delivery(first, "read"))
    emit(events.message_delivery_updated, delivery(first, "delivered"))
    emit(events.message_delivery_updated, delivery(first, "sent"))
    emit(events.message_delivery_updated, delivery(first, "read"))  # webhook retry
    emit(events.message_delivery_updated, delivery(first, "failed", error_code="131026"))

    first = reload(first)
    assert first.status == "read"
    assert first.sent_at and first.delivered_at and first.read_at
    assert first.error_code == ""
    campaign = reload(campaign)
    assert campaign.status == Campaign.Status.RUNNING
    assert campaign.stats == {
        "total": 2,
        "skipped": 0,
        "queued": 1,
        "sent": 1,
        "delivered": 1,
        "read": 1,
        "failed": 0,
        "replied": 0,
    }


def test_campaign_completes_when_no_recipient_is_queued(queued, emit):
    campaign, (first, second) = queued(2)

    emit(events.message_delivery_updated, delivery(first, "failed", error_code="131026"))
    assert reload(first).status == "failed"
    assert reload(campaign).stats["failed"] == 1

    emit(events.message_delivery_updated, delivery(second, "sent"))
    campaign = reload(campaign)
    assert campaign.status == Campaign.Status.COMPLETED
    assert campaign.completed_at is not None

    # A late delivered status beats the earlier failure, and stats follow.
    emit(events.message_delivery_updated, delivery(first, "delivered"))
    first = reload(first)
    assert (first.status, first.error_code) == ("delivered", "")
    assert reload(campaign).stats | {"total": 0} == {
        "total": 0,
        "skipped": 0,
        "queued": 0,
        "sent": 2,
        "delivered": 1,
        "read": 0,
        "failed": 0,
        "replied": 0,
    }


def test_campaign_fails_when_nothing_was_sent(queued, emit):
    campaign, (recipient,) = queued(1)

    emit(events.message_delivery_updated, delivery(recipient, "failed", error_code="131026"))

    campaign = reload(campaign)
    assert campaign.status == Campaign.Status.FAILED
    assert campaign.last_error


def test_per_user_marketing_limit_is_readable(queued, emit):
    campaign, (first, second) = queued(2)

    emit(events.message_delivery_updated, delivery(first, "failed", error_code="131049"))
    emit(events.message_delivery_updated, delivery(second, "delivered"))

    first = reload(first)
    assert (first.status, first.error_code, first.skip_reason) == (
        "failed",
        "131049",
        "per_user_marketing_limit",
    )
    campaign = reload(campaign)
    assert campaign.last_error == services.MARKETING_LIMIT_MESSAGE
    assert campaign.status == Campaign.Status.COMPLETED


def test_dispatch_policy_failure_skips_the_recipient(queued, emit):
    campaign, (first, _) = queued(2)

    emit(
        events.message_delivery_updated,
        delivery(first, "failed", error_code="contact_opted_out"),
    )

    assert (reload(first).status, first.skip_reason) == ("skipped", "opted_out")
    assert reload(campaign).stats | {"total": 0} == {
        "total": 0,
        "skipped": 1,
        "queued": 1,
        "sent": 0,
        "delivered": 0,
        "read": 0,
        "failed": 0,
        "replied": 0,
    }


def test_blocking_dispatch_failure_pauses_the_campaign(queued, emit):
    campaign, (first, _) = queued(2)

    emit(
        events.message_delivery_updated,
        delivery(first, "failed", error_code="template_not_approved"),
    )

    campaign = reload(campaign)
    assert campaign.status == Campaign.Status.PAUSED
    assert "no longer approved" in campaign.last_error


def test_other_sources_are_ignored(queued, emit):
    _, (first, _) = queued(2)

    emit(events.message_delivery_updated, delivery(first, "sent", source="inbox"))

    assert reload(first).status == "queued"


# --- Replies --------------------------------------------------------------------------------------


def test_replies_count_once_within_72_hours(queued, emit):
    campaign, (first, second) = queued(2)
    emit(events.message_delivery_updated, delivery(first, "sent"))
    emit(
        events.message_delivery_updated,
        delivery(second, "sent", at=timezone.now() - timedelta(hours=80)),
    )

    emit(events.message_recorded, inbound(first))
    emit(events.message_recorded, inbound(first))
    emit(events.message_recorded, inbound(first, direction="outbound"))
    emit(events.message_recorded, inbound(second))  # sent 80 hours ago

    assert reload(first).replied_at is not None
    assert reload(second).replied_at is None
    assert reload(campaign).stats["replied"] == 1


def test_unsent_recipients_have_no_replies(queued, emit):
    campaign, (first,) = queued(1)

    emit(events.message_recorded, inbound(first))

    assert reload(first).replied_at is None
    assert reload(campaign).stats["replied"] == 0


# --- Meta events pause campaigns ------------------------------------------------------------------


@pytest.fixture
def active(launched, template):
    """(running, scheduled) campaigns sharing ``template`` (Meta id 900001)."""
    template.meta_template_id = "900001"
    template.save(update_fields=["meta_template_id"])
    running, _ = launched(1)
    scheduled, _ = launched(1, scheduled_at=timezone.now() + timedelta(hours=1))
    return running, scheduled


def assert_paused(*campaigns, paused=True):
    for campaign in campaigns:
        campaign = reload(campaign)
        assert (campaign.status == Campaign.Status.PAUSED) is paused, campaign.status
        assert bool(campaign.last_error) is paused


def template_event(workspace, name, **fields):
    return events.TemplateStatusUpdate(
        workspace_id=workspace.pk,
        waba_id="1",
        meta_template_id="900001",
        name="order_update",
        language="en",
        event=name,
        **fields,
    )


def test_template_disabled_pauses_active_campaigns(active, workspace, number, template, emit):
    running, scheduled = active
    other_draft = CampaignFactory(phone_number=number, template=template)

    for name in ("APPROVED", "FLAGGED", "REINSTATED"):
        emit(events.template_status_updated, template_event(workspace, name))
    assert_paused(running, scheduled, paused=False)

    emit(events.template_status_updated, template_event(workspace, "DISABLED"))
    emit(events.template_status_updated, template_event(workspace, "DISABLED"))

    assert_paused(running, scheduled)
    assert "DISABLED" in reload(running).last_error
    assert reload(other_draft).status == Campaign.Status.DRAFT


def test_template_events_of_other_workspaces_are_ignored(active, other_workspace, emit):
    emit(events.template_status_updated, template_event(other_workspace, "PAUSED"))

    assert_paused(*active, paused=False)


def test_template_category_change_pauses(active, workspace, emit):
    def category(previous, new):
        return events.TemplateCategoryUpdate(
            workspace_id=workspace.pk,
            waba_id="1",
            meta_template_id="900001",
            name="order_update",
            language="en",
            previous_category=previous,
            new_category=new,
        )

    emit(events.template_category_updated, category("MARKETING", "MARKETING"))
    assert_paused(*active, paused=False)

    emit(events.template_category_updated, category("UTILITY", "MARKETING"))
    assert_paused(*active)


def test_phone_quality_downgrade_pauses(active, workspace, number, emit):
    def quality(name, display):
        return events.PhoneNumberQualityUpdate(
            workspace_id=workspace.pk,
            waba_id=number.waba.waba_id,
            display_phone_number=display,
            event=name,
        )

    digits = "".join(ch for ch in number.display_phone_number if ch.isdigit())
    emit(events.phone_number_quality_updated, quality("UPGRADE", digits))
    emit(events.phone_number_quality_updated, quality("DOWNGRADE", "919999999999"))
    assert_paused(*active, paused=False)

    emit(events.phone_number_quality_updated, quality("DOWNGRADE", digits))
    assert_paused(*active)


def test_account_restriction_pauses(active, workspace, number, emit):
    def account(name, payload=None, waba_id=None):
        return events.AccountUpdate(
            workspace_id=workspace.pk,
            waba_id=waba_id or number.waba.waba_id,
            event=name,
            payload=payload or {},
        )

    emit(events.account_updated, account("VERIFIED_ACCOUNT"))
    emit(events.account_updated, account("ACCOUNT_RESTRICTION", {"restriction_info": []}))
    emit(
        events.account_updated,
        account("DISABLED_UPDATE", {"ban_info": {"waba_ban_state": "REINSTATE"}}),
    )
    emit(events.account_updated, account("ACCOUNT_VIOLATION", waba_id="999"))
    assert_paused(*active, paused=False)

    restriction = {"restriction_info": [{"restriction_type": "RESTRICTED_BIZ_INITIATED_MESSAGING"}]}
    emit(events.account_updated, account("ACCOUNT_RESTRICTION", restriction))
    assert_paused(*active)


# --- Realtime -------------------------------------------------------------------------------------


def test_progress_broadcasts_are_throttled(queued, emit, monkeypatch):
    campaign, (first, second, third) = queued(3)
    frames = []
    monkeypatch.setattr(
        realtime, "broadcast", lambda workspace_id, type, data: frames.append((type, data))
    )
    cache.delete(services._progress_key(campaign.pk))

    emit(events.message_delivery_updated, delivery(first, "sent"))
    emit(events.message_delivery_updated, delivery(second, "sent"))  # within the window
    assert len(frames) == 1
    type_, data = frames[0]
    assert type_ == "campaign.progress"
    assert data["campaign_id"] == campaign.pk
    assert data["status"] == "running"
    assert data["stats"]["sent"] == 1

    services.pause(campaign)  # status changes always broadcast
    assert [frame[1]["status"] for frame in frames] == ["running", "paused"]

    cache.delete(services._progress_key(campaign.pk))  # the window expired
    emit(events.message_delivery_updated, delivery(third, "sent"))
    assert len(frames) == 3
    assert frames[-1][1]["stats"]["sent"] == 3


def test_recipient_rows_track_the_message(queued):
    campaign, recipients = queued(2)

    assert (
        CampaignRecipient.objects.filter(
            workspace=campaign.workspace, message__in=[r.message for r in recipients]
        ).count()
        == 2
    )
