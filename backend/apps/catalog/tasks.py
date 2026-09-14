"""Catalog Celery tasks (docs/contracts/wave-3-commerce.md, "Celery")."""

import logging

from celery import shared_task
from django.core.cache import cache

from apps.whatsapp.client import GraphAPIError

from . import sync
from .models import MetaCatalog

logger = logging.getLogger(__name__)

MAX_SYNC_RETRIES = 6


@shared_task(bind=True, name="catalog.sync_products", max_retries=MAX_SYNC_RETRIES)
def sync_products(
    self, meta_catalog_pk: str, full: bool = False, delete_retailer_ids: list[str] | None = None
) -> None:
    """Send changed products (or all with ``full``) and ``delete_retailer_ids`` to Meta.

    Rate limits (error 80014) and transient errors retry with exponential backoff.
    """
    if not delete_retailer_ids:
        # Changes saved from now on queue another run.
        cache.delete(sync.debounce_key(meta_catalog_pk))
    meta_catalog = (
        MetaCatalog.objects.select_related("waba", "workspace").filter(pk=meta_catalog_pk).first()
    )
    if meta_catalog is None or meta_catalog.status != MetaCatalog.Status.CONNECTED:
        return
    if not sync.waba_can_sync(meta_catalog.waba):
        sync.record_failure(meta_catalog, "Reconnect WhatsApp to sync the catalog.")
        return
    try:
        sync.run_sync(meta_catalog, full=full, delete_retailer_ids=delete_retailer_ids or ())
    except GraphAPIError as exc:
        retryable = exc.retryable or sync.is_rate_limited(exc)
        if retryable and self.request.retries < self.max_retries:
            countdown = sync.backoff_seconds(self.request.retries, exc)
            logger.info(
                "Catalog sync for %s backs off %ss: %s (code=%s)",
                meta_catalog.catalog_id,
                countdown,
                type(exc).__name__,
                exc.code,
            )
            raise self.retry(exc=exc, countdown=countdown) from None
        sync.record_failure(meta_catalog, exc)
    except sync.SyncBlocked as exc:
        sync.record_failure(meta_catalog, str(exc))


@shared_task(name="catalog.poll_sync_status")
def poll_sync_status() -> None:
    """Beat every 2 minutes: finish pending batches and refresh product review statuses."""
    sync.poll_pending_batches()
