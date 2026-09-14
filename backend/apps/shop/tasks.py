"""Shop Celery tasks."""

from celery import shared_task
from django.db import OperationalError

from . import services


@shared_task(
    name="shop.handle_inbound",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=3,
)
def handle_inbound(message_id: str, reply_id: str | None = None) -> bool:
    """Answer an inbound message with the buyer bot. Idempotent on the message's wamid."""
    return services.handle_inbound(message_id, reply_id=reply_id)
