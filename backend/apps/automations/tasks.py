"""Automation Celery tasks."""

from celery import shared_task
from django.db import OperationalError

from . import consent, engine


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


@shared_task(
    name="automations.handle_consent_reply",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=3,
)
def handle_consent_reply(message_id: str, reply_id: str) -> str | None:
    """Record a tap on an opt-in button and reply. Idempotent: safe to run repeatedly."""
    return consent.handle_reply(message_id, reply_id)
