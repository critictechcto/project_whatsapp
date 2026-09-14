import logging

from celery import shared_task

from apps.whatsapp.client.errors import GraphAPIError
from apps.whatsapp.models import WhatsAppBusinessAccount

from . import services

logger = logging.getLogger(__name__)

SYNC_MAX_RETRIES = 5
SYNC_MAX_BACKOFF_SECONDS = 3600


@shared_task(bind=True, name="message_templates.sync_waba", max_retries=SYNC_MAX_RETRIES)
def sync_waba(self, waba_pk: str) -> dict | None:
    """Mirror a WABA's templates from Meta. Safe to run repeatedly."""
    waba = WhatsAppBusinessAccount.objects.filter(pk=waba_pk).first()
    if waba is None or not services.is_connected(waba):
        return None
    try:
        result = services.sync_waba(waba)
    except GraphAPIError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            countdown = exc.retry_after or min(
                60 * 2**self.request.retries, SYNC_MAX_BACKOFF_SECONDS
            )
            raise self.retry(exc=exc, countdown=countdown) from exc
        logger.warning("Template sync failed for WABA %s: %s", waba.waba_id, exc)
        if exc.retryable:
            raise
        return None
    return {"created": result.created, "updated": result.updated, "deleted": result.deleted}


@shared_task(bind=True, name="message_templates.sync_all")
def sync_all(self) -> int:
    """Queue a template sync for every connected (active or restricted) WABA."""
    waba_pks = WhatsAppBusinessAccount.objects.filter(
        status__in=services.CONNECTED_WABA_STATUSES
    ).values_list("pk", flat=True)
    count = 0
    for waba_pk in waba_pks:
        sync_waba.delay(str(waba_pk))
        count += 1
    return count
