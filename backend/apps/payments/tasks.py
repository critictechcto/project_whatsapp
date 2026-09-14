"""Payments Celery tasks: on-demand link creation and status polling (no webhook needed)."""

import logging
from datetime import datetime

from celery import shared_task
from django.utils.dateparse import parse_datetime

from apps.tenants.models import Workspace

from . import services
from .exceptions import PaymentAccountInvalid, PaymentAccountMissing, PaymentProviderError

logger = logging.getLogger(__name__)

CREATE_MAX_RETRIES = 5


@shared_task(bind=True, name="payments.create_link", max_retries=CREATE_MAX_RETRIES)
def create_link(
    self,
    workspace_id: str,
    order_id: str,
    reference_id: str,
    amount_paise: int,
    description: str,
    customer_name: str,
    customer_phone_e164: str,
    expire_by: str | datetime,
) -> str | None:
    """Create a payment link (idempotent on ``reference_id``); returns its id, or None."""
    workspace = Workspace.objects.filter(pk=workspace_id).first()
    if workspace is None:
        return None
    if isinstance(expire_by, str):
        expire_by = parse_datetime(expire_by)
    try:
        link = services.create_payment_link(
            workspace=workspace,
            order_id=order_id,
            reference_id=reference_id,
            amount_paise=amount_paise,
            description=description,
            customer_name=customer_name,
            customer_phone_e164=customer_phone_e164,
            expire_by=expire_by,
        )
    except PaymentProviderError as exc:
        if exc.retryable:
            raise self.retry(countdown=min(300, 15 * 2**self.request.retries)) from None
        logger.warning("Payment link %s not created: %s", reference_id, exc)
        return None
    except (PaymentAccountMissing, PaymentAccountInvalid) as exc:
        logger.info("Payment link %s not created: %s", reference_id, exc.detail)
        return None
    return str(link.pk)


@shared_task(name="payments.poll_open_links")
def poll_open_links() -> int:
    return services.poll_due_links()
