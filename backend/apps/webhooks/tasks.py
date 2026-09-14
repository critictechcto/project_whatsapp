"""Processing of stored webhook deliveries: routing to workspaces and emitting domain events."""

import logging
import uuid
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.events import emit

from .models import WebhookEvent
from .parsers import ParsedChange, parse_payload

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
STUCK_AFTER = timedelta(minutes=15)
REQUEUE_BATCH_SIZE = 500
PURGE_BATCH_SIZE = 1000
LAST_ERROR_MAX_LENGTH = 10_000

Status = WebhookEvent.Status


class WebhookProcessingError(Exception):
    """One or more receivers failed for a webhook event; the task is retried."""


class WorkspaceResolver:
    """Maps a change to a workspace id: phone number first, then WABA. Caches per delivery."""

    def __init__(self) -> None:
        self._phones: dict[str, uuid.UUID | None] = {}
        self._wabas: dict[str, uuid.UUID | None] = {}

    def resolve(self, change: ParsedChange) -> uuid.UUID | None:
        if change.phone_number_id:
            workspace_id = self._lookup(
                self._phones, PhoneNumber, "phone_number_id", change.phone_number_id
            )
            if workspace_id is not None:
                return workspace_id
        if change.waba_id:
            return self._lookup(self._wabas, WhatsAppBusinessAccount, "waba_id", change.waba_id)
        return None

    @staticmethod
    def _lookup(cache: dict, model, field: str, value: str) -> uuid.UUID | None:
        if value not in cache:
            cache[value] = (
                model.objects.filter(**{field: value})
                .values_list("workspace_id", flat=True)
                .first()
            )
        return cache[value]


def claim_event(event_pk) -> bool:
    """Atomically move a received/failed row to processing. False if someone else has it."""
    claimed = WebhookEvent.objects.filter(
        pk=event_pk, status__in=[Status.RECEIVED, Status.FAILED]
    ).update(status=Status.PROCESSING, attempts=F("attempts") + 1, updated_at=timezone.now())
    return claimed == 1


def enqueue_on_commit(event_pk) -> None:
    """Enqueue processing after commit. Robust: a broker outage is logged, not raised, and
    ``requeue_stuck_events`` picks the row up later."""

    def enqueue_webhook_event() -> None:
        process_event.delay(str(event_pk))

    transaction.on_commit(enqueue_webhook_event, robust=True)


def _receiver_name(receiver: object) -> str:
    module = getattr(receiver, "__module__", "") or ""
    name = getattr(receiver, "__qualname__", None) or type(receiver).__qualname__
    return f"{module}.{name}" if module else name


@shared_task(bind=True, name="webhooks.process_event", max_retries=MAX_RETRIES)
def process_event(self, event_pk: str) -> str | None:
    """Route one stored delivery and emit its events. Idempotent and safe to run concurrently."""
    if not claim_event(event_pk):
        logger.info("Webhook event %s already handled or in flight", event_pk)
        return None
    event = WebhookEvent.objects.get(pk=event_pk)

    try:
        changes = parse_payload(event.payload)
    except Exception as exc:
        # Parsing is deterministic, so retrying cannot help; the admin can reprocess after a fix.
        logger.exception("Failed to parse webhook event %s", event.pk)
        _finish(event, Status.FAILED, last_error=f"Parse error: {exc!r}")
        return Status.FAILED

    resolver = WorkspaceResolver()
    first_workspace_id: uuid.UUID | None = None
    routed = 0
    errors: list[str] = []
    for change in changes:
        workspace_id = resolver.resolve(change)
        if workspace_id is None:
            logger.warning(
                "Unroutable %s change (phone_number_id=%s, waba_id=%s) in webhook event %s",
                change.field_name,
                change.phone_number_id,
                change.waba_id,
                event.pk,
            )
            continue
        routed += 1
        first_workspace_id = first_workspace_id or workspace_id
        domain_event = change.build(workspace_id=workspace_id, webhook_event_id=event.pk)
        # No surrounding transaction: receivers manage their own.
        for receiver, exc in emit(change.signal, domain_event):
            errors.append(f"{type(domain_event).__name__} -> {_receiver_name(receiver)}: {exc!r}")

    if errors:
        last_error = "\n".join(errors)
        _finish(event, Status.FAILED, last_error=last_error, workspace_id=first_workspace_id)
        countdown = min(60 * 2**self.request.retries, 3600)
        raise self.retry(
            exc=WebhookProcessingError(last_error[:1000]),
            countdown=countdown,
            max_retries=MAX_RETRIES,
        )

    status = Status.PROCESSED if routed else Status.UNROUTABLE
    _finish(event, status, workspace_id=first_workspace_id)
    return status


def _finish(
    event: WebhookEvent,
    status: str,
    *,
    last_error: str = "",
    workspace_id: uuid.UUID | None = None,
) -> None:
    now = timezone.now()
    values: dict = {
        "status": status,
        "last_error": last_error[:LAST_ERROR_MAX_LENGTH],
        "updated_at": now,
    }
    if status != Status.FAILED:
        values["processed_at"] = now
    if workspace_id is not None:
        values["workspace_id"] = workspace_id
    # Only the claimant may finish: skip if the row was requeued meanwhile.
    WebhookEvent.objects.filter(pk=event.pk, status=Status.PROCESSING).update(**values)


@shared_task(bind=True, name="webhooks.requeue_stuck_events")
def requeue_stuck_events(self) -> int:
    """Re-enqueue rows stuck in processing (worker died) or never enqueued (broker outage)."""
    now = timezone.now()
    cutoff = now - STUCK_AFTER
    with transaction.atomic():
        pks = list(
            WebhookEvent.objects.filter(
                status__in=[Status.PROCESSING, Status.RECEIVED], updated_at__lt=cutoff
            )
            .order_by("updated_at")
            .select_for_update(skip_locked=True)
            .values_list("pk", flat=True)[:REQUEUE_BATCH_SIZE]
        )
        if pks:
            WebhookEvent.objects.filter(pk__in=pks).update(status=Status.RECEIVED, updated_at=now)
            for pk in pks:
                enqueue_on_commit(pk)
    if pks:
        logger.warning("Requeued %d stuck webhook events", len(pks))
    return len(pks)


@shared_task(bind=True, name="webhooks.purge_old_events")
def purge_old_events(self) -> int:
    """Delete processed/unroutable rows older than WEBHOOK_EVENT_RETENTION_DAYS."""
    days = int(getattr(settings, "WEBHOOK_EVENT_RETENTION_DAYS", 30))
    cutoff = timezone.now() - timedelta(days=days)
    old = WebhookEvent.objects.filter(
        status__in=[Status.PROCESSED, Status.UNROUTABLE], created_at__lt=cutoff
    ).order_by()
    total = 0
    while True:
        pks = list(old.values_list("pk", flat=True)[:PURGE_BATCH_SIZE])
        if not pks:
            break
        deleted, _ = WebhookEvent.objects.filter(pk__in=pks).delete()
        total += deleted
        if deleted == 0:
            break
    if total:
        logger.info("Purged %d webhook events older than %d days", total, days)
    return total
