"""Offers Celery tasks."""

from celery import shared_task
from django.db import OperationalError

from . import services


@shared_task(
    name="offers.handle_code_message",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=3,
)
def handle_code_message(message_id: str) -> bool:
    """Record the claim for an inbound offer code and reply. Idempotent on the wamid."""
    return services.handle_code_message(message_id) is not None


@shared_task(name="offers.expire_claims")
def expire_claims() -> int:
    """Nightly: unapplied claims of ended offers become ``expired``."""
    return services.expire_claims()
