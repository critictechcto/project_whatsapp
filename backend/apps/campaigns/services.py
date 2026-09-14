"""Campaign operations shared by the API, Celery tasks and signal receivers.

State changes lock the campaign row. Stats counters change atomically with ``F()`` deltas in the
same transaction as the recipient status they reflect; ``recompute_stats`` rebuilds them from the
recipient rows when a campaign finishes.
"""

import logging
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import timedelta
from decimal import Decimal
from functools import reduce
from operator import or_
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, F, Q, QuerySet, Value
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.billing import entitlements
from apps.contacts.models import Contact, Tag
from apps.inbox import sending
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.models import PhoneNumber
from common import realtime
from common.exceptions import Conflict

from . import variables
from .models import Campaign, CampaignRecipient

logger = logging.getLogger(__name__)

CampaignStatus = Campaign.Status
RecipientStatus = CampaignRecipient.Status
SkipReason = CampaignRecipient.SkipReason

PROGRESS_EVENT = "campaign.progress"
PROGRESS_THROTTLE_SECONDS = 3
REPLY_WINDOW = timedelta(hours=72)
MATERIALISE_CHUNK_SIZE = 1000
# Pause between batches; long ETAs are avoided so paused/cancelled campaigns stop promptly.
BATCH_COUNTDOWN_SECONDS = 2
# How long a scheduled batch blocks another from being scheduled if its task is lost.
BATCH_LOCK_GRACE_SECONDS = 120

MARKETING_LIMIT_ERROR = "131049"
MARKETING_LIMIT_MESSAGE = (
    "Meta did not deliver some messages because those recipients reached Meta's per-user "
    "marketing message limit (error 131049). Meta may deliver to them in a later campaign."
)
# Dispatch-time policy failures that mean the contact should be skipped, not counted as failed.
POLICY_SKIP_CODES = {
    "contact_opted_out": SkipReason.OPTED_OUT,
    "marketing_opt_in_required": SkipReason.NOT_OPTED_IN,
}
# Dispatch-time failures that stop the whole campaign.
BLOCKING_ERROR_MESSAGES = {
    "template_not_approved": "The template is no longer approved by Meta. Sending was paused.",
    "whatsapp_not_connected": "The WhatsApp Business Account must be reconnected. Sending was "
    "paused.",
    "phone_number_not_registered": "The sending number is not registered with the Cloud API. "
    "Sending was paused.",
}

UNSET: Any = object()


# --- Errors -------------------------------------------------------------------------------------


class CampaignNotEditable(Conflict):
    default_code = "campaign_not_editable"
    default_detail = "Only draft and scheduled campaigns can be changed."


class InvalidCampaignTransition(Conflict):
    default_code = "invalid_campaign_transition"
    default_detail = "The campaign can't make that change in its current status."


class FeatureNotAvailable(Conflict):
    default_code = "feature_not_available"
    default_detail = "Scheduling campaigns isn't included in your plan. Upgrade to schedule."


# --- Stats and realtime -------------------------------------------------------------------------

_STAT_BUCKETS: dict[str, tuple[str, ...]] = {
    RecipientStatus.PENDING: (),
    RecipientStatus.SKIPPED: ("skipped_count",),
    RecipientStatus.QUEUED: ("queued_count",),
    RecipientStatus.SENT: ("sent_count",),
    RecipientStatus.DELIVERED: ("sent_count", "delivered_count"),
    RecipientStatus.READ: ("sent_count", "delivered_count", "read_count"),
    RecipientStatus.FAILED: ("failed_count",),
}


def transition_delta(old: str, new: str) -> Counter:
    """Counter changes for one recipient moving from ``old`` to ``new``."""
    delta: Counter = Counter()
    for name in _STAT_BUCKETS[old]:
        delta[name] -= 1
    for name in _STAT_BUCKETS[new]:
        delta[name] += 1
    return delta


def apply_stats(campaign_id, delta: Mapping[str, int]) -> None:
    updates = {
        name: Greatest(F(name) + amount, Value(0)) for name, amount in delta.items() if amount
    }
    if updates:
        Campaign.objects.filter(pk=campaign_id).update(**updates, updated_at=timezone.now())


def recompute_stats(campaign_id) -> None:
    """Rebuild every counter from the recipient rows."""
    rows = (
        CampaignRecipient.objects.filter(campaign_id=campaign_id)
        .values("status")
        .annotate(count=Count("pk"))
    )
    counts = {row["status"]: row["count"] for row in rows}
    read = counts.get(RecipientStatus.READ, 0)
    delivered = counts.get(RecipientStatus.DELIVERED, 0) + read
    replied = CampaignRecipient.objects.filter(
        campaign_id=campaign_id, replied_at__isnull=False
    ).count()
    Campaign.objects.filter(pk=campaign_id).update(
        total_count=sum(counts.values()),
        skipped_count=counts.get(RecipientStatus.SKIPPED, 0),
        queued_count=counts.get(RecipientStatus.QUEUED, 0),
        sent_count=counts.get(RecipientStatus.SENT, 0) + delivered,
        delivered_count=delivered,
        read_count=read,
        failed_count=counts.get(RecipientStatus.FAILED, 0),
        replied_count=replied,
        updated_at=timezone.now(),
    )


def _progress_key(campaign_id) -> str:
    return f"campaigns:progress:{campaign_id}"


def broadcast_progress(campaign_id, *, force: bool = False) -> bool:
    """Send ``campaign.progress`` on commit, at most once per throttle window unless ``force``
    (status changes always force). Returns whether a frame was queued."""
    key = _progress_key(campaign_id)
    if force:
        cache.set(key, 1, timeout=PROGRESS_THROTTLE_SECONDS)
    elif not cache.add(key, 1, timeout=PROGRESS_THROTTLE_SECONDS):
        return False
    campaign = Campaign.objects.filter(pk=campaign_id).first()
    if campaign is None:
        return False
    realtime.broadcast(
        campaign.workspace_id,
        PROGRESS_EVENT,
        {"campaign_id": campaign.pk, "status": campaign.status, "stats": campaign.stats},
    )
    return True


# --- Batch scheduling ---------------------------------------------------------------------------


def batch_lock_key(campaign_id) -> str:
    return f"campaigns:batch-scheduled:{campaign_id}"


def kick_batch(campaign_id, *, countdown: int = 0) -> None:
    """Schedule ``campaigns.send_batch`` on commit unless one is already scheduled.

    The cache key is cleared when the task starts, so duplicate chains collapse into one.
    """
    from .tasks import send_batch

    campaign_id = str(campaign_id)

    def schedule() -> None:
        if cache.add(batch_lock_key(campaign_id), 1, timeout=countdown + BATCH_LOCK_GRACE_SECONDS):
            send_batch.apply_async(args=[campaign_id], countdown=countdown)

    transaction.on_commit(schedule, robust=True)


# --- Audience -----------------------------------------------------------------------------------

_CONTACT_FIELDS = (
    "id",
    "workspace",
    "name",
    "phone_e164",
    "email",
    "wa_id",
    "attributes",
    "marketing_opt_in_status",
    "opted_in_at",
    "opted_out_at",
)


def audience_contacts(workspace_id, audience: Mapping[str, Any]) -> QuerySet[Contact]:
    """Contacts with the audience's tags (any or all of them) plus the listed contacts."""
    tag_ids = list(dict.fromkeys(str(pk) for pk in audience.get("tag_ids") or []))
    contact_ids = [str(pk) for pk in audience.get("contact_ids") or []]
    conditions = []
    if contact_ids:
        conditions.append(Q(pk__in=contact_ids))
    if tag_ids:
        tagged = Contact.objects.filter(workspace_id=workspace_id, tags__in=tag_ids)
        if audience.get("match") == "all":
            tagged = (
                tagged.values("pk")
                .annotate(matched=Count("tags", distinct=True))
                .filter(matched=len(tag_ids))
            )
        conditions.append(Q(pk__in=tagged.values("pk")))
    if not conditions:
        return Contact.objects.none()
    return Contact.objects.filter(workspace_id=workspace_id).filter(reduce(or_, conditions))


def consent_skip_reason(contact: Contact, category: str) -> str | None:
    """Why ``contact`` can't receive a template of ``category`` right now (None when it can)."""
    if contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT:
        return SkipReason.OPTED_OUT
    if (
        category == MessageTemplate.Category.MARKETING
        and contact.marketing_opt_in_status != Contact.OptInStatus.OPTED_IN
    ):
        return SkipReason.NOT_OPTED_IN
    if not contact.wa_id:
        return SkipReason.INVALID
    return None


def _template_category(campaign: Campaign) -> str:
    if campaign.template is not None:
        return campaign.template.category
    return str((campaign.template_snapshot or {}).get("category") or "")


def _evaluate(campaign: Campaign) -> Iterator[tuple[Contact, str | None, dict | None]]:
    """``(contact, skip_reason, params)`` for every contact in the audience."""
    category = _template_category(campaign)
    mapping = campaign.variable_mapping or {}
    contacts = (
        audience_contacts(campaign.workspace_id, campaign.audience or {})
        .only(*_CONTACT_FIELDS)
        .order_by("pk")
    )
    for contact in contacts.iterator(chunk_size=2000):
        reason = consent_skip_reason(contact, category)
        params = None
        if reason is None:
            params = variables.resolve_params(mapping, contact)
            if params is None:
                reason = SkipReason.MISSING_VARIABLE
        yield contact, reason, params


def audience_preview(campaign: Campaign) -> dict[str, Any]:
    counts: Counter = Counter(reason for _, reason, _ in _evaluate(campaign))
    return {
        "total": sum(counts.values()),
        "eligible": counts[None],
        "skipped": {
            "opted_out": counts[SkipReason.OPTED_OUT],
            "not_opted_in": counts[SkipReason.NOT_OPTED_IN],
            "invalid": counts[SkipReason.INVALID] + counts[SkipReason.MISSING_VARIABLE],
        },
    }


def _materialise(campaign: Campaign) -> int:
    """Replace the campaign's recipients from its audience; sets counters on ``campaign`` (not
    saved). Returns the number of eligible (pending) recipients."""
    CampaignRecipient.objects.filter(campaign=campaign).delete()
    counts: Counter = Counter()
    chunk: list[CampaignRecipient] = []
    for contact, reason, params in _evaluate(campaign):
        counts[reason] += 1
        chunk.append(
            CampaignRecipient(
                workspace_id=campaign.workspace_id,
                campaign=campaign,
                contact_id=contact.pk,
                status=RecipientStatus.SKIPPED if reason else RecipientStatus.PENDING,
                skip_reason=reason or "",
                params=params or {},
                consent_status=contact.marketing_opt_in_status,
                consent_opted_in_at=contact.opted_in_at,
                consent_opted_out_at=contact.opted_out_at,
            )
        )
        if len(chunk) >= MATERIALISE_CHUNK_SIZE:
            CampaignRecipient.objects.bulk_create(chunk)
            chunk = []
    if chunk:
        CampaignRecipient.objects.bulk_create(chunk)
    total = sum(counts.values())
    eligible = counts[None]
    for name in Campaign.STAT_FIELDS.values():
        setattr(campaign, name, 0)
    campaign.total_count = total
    campaign.skipped_count = total - eligible
    return eligible


def estimate_cost(category: str, eligible: int) -> Decimal:
    rate = Decimal(str(settings.WHATSAPP_RATE_CARD_INR.get(category, "0")))
    return (rate * eligible).quantize(Decimal("0.0001"))


# --- Create, update, delete ---------------------------------------------------------------------


def template_snapshot(template: MessageTemplate) -> dict[str, str]:
    return {
        "id": str(template.pk),
        "name": template.name,
        "language": template.language,
        "category": template.category,
    }


def write_representation(campaign: Campaign) -> dict[str, Any]:
    """The campaign as ``CampaignWriteRequest`` data, for merging a PATCH body into."""
    return {
        "name": campaign.name,
        "template_id": campaign.template_id,
        "phone_number_id": campaign.phone_number_id,
        "audience": campaign.audience or {},
        "variable_mapping": campaign.variable_mapping or {},
        "scheduled_at": campaign.scheduled_at,
    }


def _normalise_audience(audience: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tag_ids": list(dict.fromkeys(str(pk) for pk in audience.get("tag_ids") or [])),
        "match": audience.get("match") or "any",
        "contact_ids": list(dict.fromkeys(str(pk) for pk in audience.get("contact_ids") or [])),
    }


def _normalise_source(source: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source": source["source"],
        "value": source["value"],
        "fallback": source.get("fallback") or "",
    }


def _normalise_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    header = mapping.get("header")
    return {
        "body": [_normalise_source(source) for source in mapping.get("body") or []],
        "header": _normalise_source(header) if header else None,
        "buttons": {
            str(int(key)): _normalise_source(source)
            for key, source in (mapping.get("buttons") or {}).items()
        },
    }


def _clean(workspace, data: Mapping[str, Any], *, changed: set[str]) -> dict[str, Any]:
    """Check workspace ownership and the variable mapping; raise field errors (400)."""
    errors: dict[str, Any] = {}

    template = (
        MessageTemplate.objects.select_related("waba")
        .filter(workspace=workspace, pk=data["template_id"])
        .first()
    )
    if template is None:
        errors["template_id"] = ["No template with this id in this workspace."]

    phone_number_id = data.get("phone_number_id")
    numbers = PhoneNumber.objects.select_related("waba").filter(workspace=workspace)
    if phone_number_id:
        phone_number = numbers.filter(pk=phone_number_id).first()
        if phone_number is None:
            errors["phone_number_id"] = ["No WhatsApp number with this id in this workspace."]
    else:
        phone_number = numbers.filter(is_default=True).first()
        if phone_number is None:
            errors["phone_number_id"] = [
                "Connect a WhatsApp number or choose which number sends this campaign."
            ]
    if (
        template is not None
        and phone_number is not None
        and template.waba_id != phone_number.waba_id
    ):
        errors["template_id"] = [
            "The template belongs to a different WhatsApp Business Account than the number."
        ]

    audience = _normalise_audience(data["audience"])
    audience_errors = {}
    known_tags = {
        str(pk)
        for pk in Tag.objects.filter(workspace=workspace, pk__in=audience["tag_ids"]).values_list(
            "pk", flat=True
        )
    }
    if missing := [pk for pk in audience["tag_ids"] if pk not in known_tags]:
        audience_errors["tag_ids"] = [f"Unknown tag ids: {', '.join(missing)}."]
    known_contacts = {
        str(pk)
        for pk in Contact.objects.filter(
            workspace=workspace, pk__in=audience["contact_ids"]
        ).values_list("pk", flat=True)
    }
    if missing := [pk for pk in audience["contact_ids"] if pk not in known_contacts]:
        audience_errors["contact_ids"] = [f"Unknown contact ids: {', '.join(missing)}."]
    if audience_errors:
        errors["audience"] = audience_errors

    mapping = _normalise_mapping(data["variable_mapping"])
    mapping_problems = (
        variables.mapping_errors(template, mapping)
        if template is not None and "template_id" not in errors
        else None
    )
    if mapping_problems:
        errors["variable_mapping"] = mapping_problems

    scheduled_at = data.get("scheduled_at")
    if "scheduled_at" in changed and scheduled_at is not None and scheduled_at <= timezone.now():
        errors["scheduled_at"] = ["Choose a time in the future."]

    if errors:
        raise ValidationError(errors)
    return {
        "name": data["name"],
        "template": template,
        "template_snapshot": template_snapshot(template),
        "phone_number": phone_number,
        "audience": audience,
        "variable_mapping": mapping,
        "scheduled_at": scheduled_at,
    }


def create_campaign(workspace, data: Mapping[str, Any], *, actor) -> Campaign:
    fields = _clean(workspace, data, changed=set(data))
    return Campaign.objects.create(
        workspace=workspace, status=CampaignStatus.DRAFT, created_by=actor, **fields
    )


def _lock(campaign_id) -> Campaign:
    return (
        Campaign.objects.select_for_update(of=("self",))
        .select_related("workspace", "template", "phone_number__waba")
        .get(pk=campaign_id)
    )


def _require_audience(campaign: Campaign) -> None:
    audience = campaign.audience or {}
    if not (audience.get("tag_ids") or audience.get("contact_ids")):
        raise ValidationError({"audience": ["Add tags or contacts to the audience first."]})


def _check_sendable(campaign: Campaign) -> MessageTemplate:
    """Template approved and matching the mapping, number connected (409 / 400 otherwise)."""
    template = campaign.template
    if template is None or template.status != MessageTemplate.Status.APPROVED:
        raise sending.TemplateNotApproved()
    sending.check_phone_number(campaign.phone_number)
    if problems := variables.mapping_errors(template, campaign.variable_mapping or {}):
        raise ValidationError({"variable_mapping": problems})
    return template


def _prepare_recipients(campaign: Campaign, template: MessageTemplate) -> None:
    eligible = _materialise(campaign)
    if eligible == 0:
        raise ValidationError(
            {"audience": ["No contact in this audience can receive this campaign."]}
        )
    campaign.estimated_cost = estimate_cost(template.category, eligible)


def _require_scheduling(campaign: Campaign) -> None:
    if not entitlements.has_feature(campaign.workspace, entitlements.SCHEDULED_CAMPAIGNS):
        raise FeatureNotAvailable()


_RECIPIENT_INPUTS = ("template_id", "phone_number_id", "audience", "variable_mapping")


def update_campaign(campaign: Campaign, data: Mapping[str, Any], *, changed: set[str]) -> Campaign:
    """Apply a validated, merged write body. Scheduled campaigns re-materialise recipients when
    the template, number, audience or mapping changes."""
    with transaction.atomic():
        campaign = _lock(campaign.pk)
        if campaign.status not in Campaign.EDITABLE_STATUSES:
            raise CampaignNotEditable()
        before = write_representation(campaign)
        fields = _clean(campaign.workspace, data, changed=changed)
        for name, value in fields.items():
            setattr(campaign, name, value)
        after = write_representation(campaign)

        if campaign.status == CampaignStatus.SCHEDULED:
            now = timezone.now()
            if campaign.scheduled_at is None or campaign.scheduled_at <= now:
                raise ValidationError(
                    {"scheduled_at": ["A scheduled campaign needs a send time in the future."]}
                )
            if before["scheduled_at"] != after["scheduled_at"]:
                _require_scheduling(campaign)
            # Sending the audience again re-evaluates it: tags may have gained contacts.
            if changed & set(_RECIPIENT_INPUTS) or any(
                before[name] != after[name] for name in _RECIPIENT_INPUTS
            ):
                _require_audience(campaign)
                template = _check_sendable(campaign)
                _prepare_recipients(campaign, template)
        campaign.save()
        if campaign.status == CampaignStatus.SCHEDULED:
            broadcast_progress(campaign.pk, force=True)
    return campaign


def delete_campaign(campaign: Campaign) -> None:
    with transaction.atomic():
        campaign = _lock(campaign.pk)
        if campaign.status != CampaignStatus.DRAFT:
            raise CampaignNotEditable("Only draft campaigns can be deleted.")
        campaign.delete()


# --- Transitions --------------------------------------------------------------------------------


def launch(campaign: Campaign, *, actor, scheduled_at=UNSET) -> Campaign:
    """Attest consent, materialise recipients and start now or at ``scheduled_at``.

    ``scheduled_at`` omitted uses the draft's own time; ``None`` or a past time sends now.
    """
    with transaction.atomic():
        campaign = _lock(campaign.pk)
        if campaign.status != CampaignStatus.DRAFT:
            raise InvalidCampaignTransition("Only draft campaigns can be launched.")
        _require_audience(campaign)
        template = _check_sendable(campaign)
        now = timezone.now()
        when = campaign.scheduled_at if scheduled_at is UNSET else scheduled_at
        schedule = when is not None and when > now
        if schedule:
            _require_scheduling(campaign)
        _prepare_recipients(campaign, template)

        campaign.consent_attested = True
        campaign.attested_by = actor
        campaign.attested_at = now
        campaign.last_error = ""
        if schedule:
            campaign.status = CampaignStatus.SCHEDULED
            campaign.scheduled_at = when
        else:
            campaign.status = CampaignStatus.RUNNING
            campaign.scheduled_at = None
            campaign.started_at = now
        campaign.save()
        broadcast_progress(campaign.pk, force=True)
        if campaign.status == CampaignStatus.RUNNING:
            kick_batch(campaign.pk)
    return campaign


def set_paused(campaign: Campaign, reason: str | None = None) -> None:
    """Pause a locked campaign. ``reason`` (automatic pauses) replaces ``last_error``."""
    campaign.status = CampaignStatus.PAUSED
    campaign.paused_at = timezone.now()
    fields = ["status", "paused_at", "updated_at"]
    if reason is not None:
        campaign.last_error = reason[:2000]
        fields.append("last_error")
    campaign.save(update_fields=fields)
    broadcast_progress(campaign.pk, force=True)


def pause(campaign: Campaign) -> Campaign:
    with transaction.atomic():
        campaign = _lock(campaign.pk)
        if campaign.status not in Campaign.PAUSABLE_STATUSES:
            raise InvalidCampaignTransition("Only scheduled or running campaigns can be paused.")
        set_paused(campaign)
    return campaign


def pause_active(campaign_ids, reason: str) -> int:
    """Pause the scheduled or running campaigns among ``campaign_ids`` (Meta events)."""
    paused = 0
    for campaign_id in campaign_ids:
        with transaction.atomic():
            campaign = Campaign.objects.select_for_update().filter(pk=campaign_id).first()
            if campaign is not None and campaign.status in Campaign.PAUSABLE_STATUSES:
                set_paused(campaign, reason)
                paused += 1
    if paused:
        logger.info("Paused %d campaign(s): %s", paused, reason)
    return paused


def resume(campaign: Campaign) -> Campaign:
    with transaction.atomic():
        campaign = _lock(campaign.pk)
        if campaign.status != CampaignStatus.PAUSED:
            raise InvalidCampaignTransition("Only paused campaigns can be resumed.")
        template = campaign.template
        if template is None or template.status != MessageTemplate.Status.APPROVED:
            raise sending.TemplateNotApproved()
        sending.check_phone_number(campaign.phone_number)
        now = timezone.now()
        never_started = campaign.started_at is None
        if never_started and campaign.scheduled_at is not None and campaign.scheduled_at > now:
            campaign.status = CampaignStatus.SCHEDULED
        else:
            campaign.status = CampaignStatus.RUNNING
            campaign.started_at = campaign.started_at or now
        campaign.paused_at = None
        campaign.last_error = ""
        campaign.save()
        broadcast_progress(campaign.pk, force=True)
        if campaign.status == CampaignStatus.RUNNING:
            kick_batch(campaign.pk)
    return campaign


def cancel(campaign: Campaign) -> Campaign:
    """Stop sending: pending recipients become skipped (``cancelled``). Messages already queued
    in the inbox still go out."""
    with transaction.atomic():
        campaign = _lock(campaign.pk)
        if campaign.status not in Campaign.CANCELLABLE_STATUSES:
            raise InvalidCampaignTransition(
                "Only scheduled, running or paused campaigns can be cancelled."
            )
        now = timezone.now()
        skipped = CampaignRecipient.objects.filter(
            campaign=campaign, status=RecipientStatus.PENDING
        ).update(status=RecipientStatus.SKIPPED, skip_reason=SkipReason.CANCELLED, updated_at=now)
        campaign.status = CampaignStatus.CANCELLED
        campaign.cancelled_at = now
        campaign.save(update_fields=["status", "cancelled_at", "updated_at"])
        apply_stats(campaign.pk, {"skipped_count": skipped})
        broadcast_progress(campaign.pk, force=True)
    return campaign


def start_scheduled(campaign_id) -> bool:
    """Move a due scheduled campaign to running and kick off its first batch."""
    with transaction.atomic():
        campaign = (
            Campaign.objects.select_for_update()
            .filter(
                pk=campaign_id,
                status=CampaignStatus.SCHEDULED,
                scheduled_at__lte=timezone.now(),
            )
            .first()
        )
        if campaign is None:
            return False
        campaign.status = CampaignStatus.RUNNING
        campaign.started_at = timezone.now()
        campaign.save(update_fields=["status", "started_at", "updated_at"])
        broadcast_progress(campaign.pk, force=True)
        kick_batch(campaign.pk)
    return True


def complete_if_done(campaign_id) -> bool:
    """Finish a running campaign once no recipient is pending or queued."""
    with transaction.atomic():
        campaign = (
            Campaign.objects.select_for_update()
            .filter(pk=campaign_id, status=CampaignStatus.RUNNING)
            .first()
        )
        if campaign is None:
            return False
        unfinished = CampaignRecipient.objects.filter(
            campaign_id=campaign_id,
            status__in=(RecipientStatus.PENDING, RecipientStatus.QUEUED),
        )
        if unfinished.exists():
            return False
        recompute_stats(campaign_id)
        campaign.refresh_from_db()
        nothing_sent = campaign.failed_count > 0 and campaign.sent_count == 0
        campaign.status = CampaignStatus.FAILED if nothing_sent else CampaignStatus.COMPLETED
        campaign.completed_at = timezone.now()
        if nothing_sent and not campaign.last_error:
            campaign.last_error = "No messages were sent. Check the recipients' error codes."
        campaign.save(update_fields=["status", "completed_at", "last_error", "updated_at"])
        broadcast_progress(campaign.pk, force=True)
    return True


# --- Delivery statuses and replies --------------------------------------------------------------

_RANK = {
    RecipientStatus.QUEUED: 0,
    RecipientStatus.SENT: 1,
    RecipientStatus.DELIVERED: 2,
    RecipientStatus.READ: 3,
}
_DELIVERY_STATUSES = frozenset(
    {
        RecipientStatus.SENT,
        RecipientStatus.DELIVERED,
        RecipientStatus.READ,
        RecipientStatus.FAILED,
    }
)


def _target_status(current: str, new: str) -> str:
    """Monotonic: queued < sent < delivered < read. ``failed`` wins over queued/sent and loses to
    a later delivered/read."""
    if current not in _RANK and current != RecipientStatus.FAILED:
        return current  # pending/skipped recipients are never linked to a message
    if new == RecipientStatus.FAILED:
        delivered = current in (RecipientStatus.DELIVERED, RecipientStatus.READ)
        return current if delivered else RecipientStatus.FAILED
    if current == RecipientStatus.FAILED:
        return new if new in (RecipientStatus.DELIVERED, RecipientStatus.READ) else current
    return new if _RANK[new] > _RANK[current] else current


def apply_delivery_update(event) -> bool:
    """Apply an inbox ``MessageDeliveryUpdated`` to its campaign recipient (idempotent)."""
    if event.source != "campaign" or event.status not in _DELIVERY_STATUSES:
        return False
    try:
        campaign_id = uuid.UUID(str(event.source_ref))
    except ValueError:
        return False
    error_code = str(event.error_code or "")
    pause_reason = None
    with transaction.atomic():
        recipient = (
            CampaignRecipient.objects.select_for_update()
            .filter(
                workspace_id=event.workspace_id,
                campaign_id=campaign_id,
                message_id=event.message_id,
            )
            .first()
        )
        if recipient is None:
            return False
        current = recipient.status
        new = event.status
        occurred_at = event.occurred_at
        updates: dict[str, Any] = {}

        if new == RecipientStatus.FAILED and current == RecipientStatus.QUEUED:
            target = RecipientStatus.FAILED
            if error_code in POLICY_SKIP_CODES:
                target = RecipientStatus.SKIPPED
        else:
            target = _target_status(current, new)

        if target not in (RecipientStatus.SKIPPED, RecipientStatus.FAILED):

            def set_once(name: str) -> None:
                if getattr(recipient, name) is None:
                    updates[name] = occurred_at

            set_once("sent_at")
            if new in (RecipientStatus.DELIVERED, RecipientStatus.READ):
                set_once("delivered_at")
            if new == RecipientStatus.READ:
                set_once("read_at")

        if target != current:
            updates["status"] = target
            if target == RecipientStatus.SKIPPED:
                updates.update(skip_reason=POLICY_SKIP_CODES[error_code], error_code=error_code)
            elif target == RecipientStatus.FAILED:
                limit = error_code == MARKETING_LIMIT_ERROR
                updates.update(
                    failed_at=occurred_at,
                    error_code=error_code[:64],
                    skip_reason=SkipReason.PER_USER_MARKETING_LIMIT if limit else "",
                )
                if limit:
                    Campaign.objects.filter(pk=campaign_id, last_error="").update(
                        last_error=MARKETING_LIMIT_MESSAGE
                    )
                pause_reason = BLOCKING_ERROR_MESSAGES.get(error_code)
            elif current == RecipientStatus.FAILED:
                updates.update(failed_at=None, error_code="", skip_reason="")

        if not updates:
            return False
        for name, value in updates.items():
            setattr(recipient, name, value)
        recipient.save(update_fields=[*updates, "updated_at"])
        if target != current:
            apply_stats(campaign_id, transition_delta(current, target))

    if target == current:
        return True
    broadcast_progress(campaign_id)
    if pause_reason:
        pause_active([campaign_id], pause_reason)
    if current == RecipientStatus.QUEUED:
        complete_if_done(campaign_id)
    return True


def record_reply(event) -> bool:
    """Count an inbound message as a reply to the latest campaign message the contact got on
    that number within :data:`REPLY_WINDOW`. Each recipient counts once."""
    if event.direction != "inbound":
        return False
    received_at = event.created_at
    recipient = (
        CampaignRecipient.objects.filter(
            workspace_id=event.workspace_id,
            contact_id=event.contact_id,
            campaign__phone_number_id=event.phone_number_id,
            campaign__status__in=(CampaignStatus.RUNNING, CampaignStatus.COMPLETED),
            sent_at__gte=received_at - REPLY_WINDOW,
            sent_at__lte=received_at,
        )
        .order_by("-sent_at")
        .values("pk", "campaign_id", "replied_at")
        .first()
    )
    if recipient is None or recipient["replied_at"] is not None:
        return False
    with transaction.atomic():
        updated = CampaignRecipient.objects.filter(
            pk=recipient["pk"], replied_at__isnull=True
        ).update(replied_at=received_at, updated_at=timezone.now())
        if updated:
            apply_stats(recipient["campaign_id"], {"replied_count": 1})
    if updated:
        broadcast_progress(recipient["campaign_id"])
    return bool(updated)
