"""Automation Celery tasks."""

from celery import shared_task
from django.db import OperationalError

from . import engine


@shared_task(
    name="automations.process_inbound",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=3,
)
def process_inbound(
    message_id: str,
    is_first_inbound: bool | None = None,
    contact_created: bool | None = None,
) -> int:
    """Evaluate automation rules for an inbound message. Idempotent: safe to run repeatedly.

    Returns the number of matched rules.
    """
    runs = engine.process_inbound(
        message_id, is_first_inbound=is_first_inbound, contact_created=contact_created
    )
    return len(runs)
