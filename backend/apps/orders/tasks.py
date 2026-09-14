"""Orders Celery tasks: payment links for online checkouts and checkout expiry."""

import logging

from celery import shared_task

from apps.payments.exceptions import (
    PaymentAccountInvalid,
    PaymentAccountMissing,
    PaymentProviderError,
)

from . import checkout

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
