"""Orders Celery tasks: payment links for online checkouts, payment reminders and their default
template, checkout expiry and booking reminders."""

import logging

from celery import shared_task
from django.db import IntegrityError
from rest_framework.exceptions import APIException

from apps.payments.exceptions import (
    PaymentAccountInvalid,
    PaymentAccountMissing,
    PaymentProviderError,
)
from apps.whatsapp.models import WhatsAppBusinessAccount

from . import checkout, lifecycle, store_setup

logger = logging.getLogger(__name__)

PAYMENT_LINK_MAX_RETRIES = 3
PAYMENT_LINK_RETRY_SECONDS = 20


@shared_task(
    bind=True,
    name="orders.send_payment_link",
    max_retries=PAYMENT_LINK_MAX_RETRIES,
    default_retry_delay=PAYMENT_LINK_RETRY_SECONDS,
)
def send_payment_link(self, order_id: str, attempt: int) -> None:
    """Create the payment link for checkout ``attempt`` and send it to the buyer.

    Retryable gateway errors are retried; when retries run out, or the seller's gateway account
    is missing or invalid, stock is released and the buyer is offered another way to pay.
    """
    try:
        checkout.create_and_send_payment_link(order_id, attempt)
    except (PaymentAccountMissing, PaymentAccountInvalid) as exc:
        logger.warning("Payment link for order %s not created: %s", order_id, exc)
        checkout.payment_link_failed(order_id, attempt, retryable=False)
    except PaymentProviderError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            countdown = PAYMENT_LINK_RETRY_SECONDS * (2**self.request.retries)
            raise self.retry(exc=exc, countdown=countdown) from exc
        logger.warning("Payment link for order %s failed: %s", order_id, exc)
        checkout.payment_link_failed(order_id, attempt, retryable=True)


@shared_task(name="orders.expire_checkouts")
def expire_checkouts() -> int:
    """Expire checkouts past their deadline (beat, every 5 minutes)."""
    return checkout.expire_checkouts()


@shared_task(name="orders.send_payment_reminders")
def send_payment_reminders() -> int:
    """Remind buyers once to pay an open payment link (beat, every 5 minutes)."""
    return checkout.send_payment_reminders()


@shared_task(name="orders.ensure_payment_reminder_template")
def ensure_payment_reminder_template(waba_id: str) -> None:
    """Create the default ``upc_payment_reminder`` template in a WABA that has none (queued when a
    payment link is sent). Failures are logged; the next payment link queues it again."""
    waba = WhatsAppBusinessAccount.objects.filter(pk=waba_id).first()
    if waba is None:
        return
    try:
        store_setup.ensure_default_template(waba, "payment_reminder")
    except (APIException, IntegrityError) as exc:
        logger.warning(
            "Default payment reminder template for WABA %s not created: %s", waba_id, exc
        )


@shared_task(name="orders.send_booking_reminders")
def send_booking_reminders() -> int:
    """Remind buyers of confirmed bookings (beat, every 10 minutes)."""
    return lifecycle.send_booking_reminders()
