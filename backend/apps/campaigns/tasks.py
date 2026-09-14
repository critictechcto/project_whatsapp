"""Campaign sending pipeline.

``campaigns.start_due`` (every minute) starts due scheduled campaigns and re-kicks running ones
whose batch chain was lost. ``campaigns.send_batch`` turns up to ``CAMPAIGN_BATCH_SIZE`` pending
recipients into queued inbox messages, dispatches them on commit and re-schedules itself a few
seconds later while recipients are pending. Duplicate or concurrent runs are safe: the campaign
row lock serialises them, pending rows are claimed with ``skip_locked`` and every message uses
the idempotency key ``campaign:<campaign_id>:recipient:<recipient_id>``.
"""

import logging
from collections import Counter

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.inbox import sending
from apps.inbox.models import Message
from apps.message_templates.models import MessageTemplate

from . import services, variables
from .models import Campaign, CampaignRecipient

logger = logging.getLogger(__name__)

CampaignStatus = Campaign.Status
RecipientStatus = CampaignRecipient.Status
SkipReason = CampaignRecipient.SkipReason

START_DUE_LIMIT = 500
WATCHDOG_LIMIT = 1000
# Policy errors that stop the whole campaign instead of failing one recipient.
BLOCKING_ERRORS = (
    sending.TemplateNotApproved,
    sending.WhatsAppNotConnected,
    sending.PhoneNumberNotRegistered,
)
_MESSAGE_TO_RECIPIENT = {
    Message.Status.QUEUED: RecipientStatus.QUEUED,
    Message.Status.SENDING: RecipientStatus.QUEUED,
    Message.Status.SENT: RecipientStatus.SENT,
    Message.Status.DELIVERED: RecipientStatus.DELIVERED,
    Message.Status.READ: RecipientStatus.READ,
    Message.Status.FAILED: RecipientStatus.FAILED,
}


class _Paused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@shared_task(name="campaigns.start_due")
def start_due() -> int:
    now = timezone.now()
    due = Campaign.objects.filter(status=CampaignStatus.SCHEDULED, scheduled_at__lte=now).order_by(
        "scheduled_at"
    )
    started = sum(
        services.start_scheduled(campaign_id)
        for campaign_id in due.values_list("pk", flat=True)[:START_DUE_LIMIT]
    )

    running = Campaign.objects.filter(status=CampaignStatus.RUNNING).order_by("started_at")
    for campaign_id in running.values_list("pk", flat=True)[:WATCHDOG_LIMIT]:
        pending = CampaignRecipient.objects.filter(
            campaign_id=campaign_id, status=RecipientStatus.PENDING
        ).exists()
        if pending:
            services.kick_batch(campaign_id)  # no-op while a batch is already scheduled
        else:
            services.complete_if_done(campaign_id)
    return started


@shared_task(name="campaigns.send_batch")
def send_batch(campaign_id: str) -> int:
    """Queue one batch of messages. Returns the number of recipients processed."""
    cache.delete(services.batch_lock_key(campaign_id))
    processed, has_pending = _send_batch(campaign_id)
    if processed is not None and not has_pending:
        services.complete_if_done(campaign_id)
    return processed or 0


def _blocking_reason(campaign: Campaign) -> str | None:
    template = campaign.template
    if template is None or template.status != MessageTemplate.Status.APPROVED:
        return "The template is no longer approved by Meta. Sending was paused."
    try:
        sending.check_phone_number(campaign.phone_number)
    except sending.SendPolicyError as exc:
        return f"{exc.detail} Sending was paused."
    return None


def _send_batch(campaign_id: str) -> tuple[int | None, bool]:
    with transaction.atomic():
        campaign = (
            Campaign.objects.select_for_update(of=("self",))
            .select_related("workspace", "template", "phone_number__waba")
            .filter(pk=campaign_id)
            .first()
        )
        if campaign is None or campaign.status != CampaignStatus.RUNNING:
            return None, False
        if reason := _blocking_reason(campaign):
            services.set_paused(campaign, reason)
            return None, False

        recipients = list(
            CampaignRecipient.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("contact")
            .filter(campaign=campaign, status=RecipientStatus.PENDING)
            .order_by("created_at", "pk")[: settings.CAMPAIGN_BATCH_SIZE]
        )
        delta: Counter = Counter()
        changed: list[CampaignRecipient] = []
        queued_ids = []
        pause_reason = None
        for recipient in recipients:
            try:
                message = _send_one(campaign, recipient)
            except _Paused as paused:
                pause_reason = paused.reason
                break
            if message is not None and message.status == Message.Status.QUEUED:
                queued_ids.append(message.pk)
            delta.update(services.transition_delta(RecipientStatus.PENDING, recipient.status))
            changed.append(recipient)

        CampaignRecipient.objects.bulk_update(
            changed,
            fields=[
                "status",
                "skip_reason",
                "error_code",
                "message",
                "queued_at",
                "sent_at",
                "failed_at",
                "updated_at",
            ],
        )
        services.apply_stats(campaign.pk, delta)
        sending.enqueue(queued_ids)

        if pause_reason:
            services.set_paused(campaign, pause_reason)
            return len(changed), True
        has_pending = CampaignRecipient.objects.filter(
            campaign=campaign, status=RecipientStatus.PENDING
        ).exists()
        if has_pending:
            services.kick_batch(campaign.pk, countdown=services.BATCH_COUNTDOWN_SECONDS)
        if changed:
            services.broadcast_progress(campaign.pk)
    return len(changed), has_pending


def _skip(recipient: CampaignRecipient, reason: str) -> None:
    recipient.status = RecipientStatus.SKIPPED
    recipient.skip_reason = reason


def _fail(recipient: CampaignRecipient, code: str) -> None:
    recipient.status = RecipientStatus.FAILED
    recipient.error_code = code[:64]
    recipient.failed_at = timezone.now()


def _send_one(campaign: Campaign, recipient: CampaignRecipient) -> Message | None:
    """Queue the recipient's message (or skip/fail it); raises :class:`_Paused` to stop."""
    recipient.updated_at = timezone.now()
    template = campaign.template
    contact = recipient.contact
    if reason := services.consent_skip_reason(contact, template.category):
        _skip(recipient, reason)
        return None
    try:
        message = sending.send_message(
            workspace=campaign.workspace,
            contact=contact,
            content=variables.template_content(template, recipient.params or {}),
            phone_number=campaign.phone_number,
            source=Message.Source.CAMPAIGN,
            source_ref=str(campaign.pk),
            idempotency_key=f"campaign:{campaign.pk}:recipient:{recipient.pk}",
            dispatch=False,
        )
    except sending.ContactOptedOut:
        _skip(recipient, SkipReason.OPTED_OUT)
        return None
    except sending.MarketingOptInRequired:
        _skip(recipient, SkipReason.NOT_OPTED_IN)
        return None
    except BLOCKING_ERRORS as exc:
        raise _Paused(f"{exc.detail} Sending was paused.") from exc
    except sending.SendPolicyError as exc:
        _fail(recipient, exc.default_code)
        return None
    except ValidationError:
        logger.info("Campaign %s recipient %s has invalid parameters", campaign.pk, recipient.pk)
        _fail(recipient, "invalid_parameters")
        return None
    except ValueError:
        logger.exception("Campaign %s recipient %s could not be queued", campaign.pk, recipient.pk)
        _fail(recipient, "invalid")
        return None

    recipient.message = message
    recipient.status = _MESSAGE_TO_RECIPIENT.get(message.status, RecipientStatus.QUEUED)
    recipient.queued_at = recipient.queued_at or message.created_at
    recipient.sent_at = message.sent_at
    if recipient.status == RecipientStatus.FAILED:
        recipient.error_code = (message.error_code or "")[:64]
        recipient.failed_at = message.failed_at
    return message
