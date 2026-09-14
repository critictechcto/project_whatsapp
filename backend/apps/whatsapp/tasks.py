import logging

from celery import shared_task
from django.utils import timezone

from . import services
from .client import GraphAPIError, get_client
from .client.errors import TokenInvalidError
from .models import PhoneNumber, WhatsAppBusinessAccount

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
MAX_BACKOFF_SECONDS = 3600


def backoff_seconds(retries: int, exc: GraphAPIError) -> int:
    if exc.retry_after:
        return min(exc.retry_after, MAX_BACKOFF_SECONDS)
    return min(30 * 2**retries, MAX_BACKOFF_SECONDS)


def _update(instance, **fields) -> None:
    for name, value in fields.items():
        setattr(instance, name, value)
    instance.save(update_fields=[*fields, "updated_at"])


@shared_task(bind=True, name="whatsapp.finish_onboarding", max_retries=MAX_RETRIES)
def finish_onboarding(self, waba_pk: str) -> None:
    """Subscribe webhooks, register numbers and refresh details. Each step is skipped when done."""
    waba = WhatsAppBusinessAccount.objects.filter(pk=waba_pk).first()
    if waba is None or waba.status == WhatsAppBusinessAccount.Status.DISCONNECTED:
        return
    if not waba.access_token:
        return
    statuses = WhatsAppBusinessAccount.OnboardingStatus
    client = get_client(waba.access_token)
    try:
        if waba.subscribed_at is None:
            _update(waba, onboarding_status=statuses.SUBSCRIBING)
            client.subscribe_app(waba.waba_id)
            _update(waba, subscribed_at=timezone.now())

        phones = list(waba.phone_numbers.all())
        for phone in phones:
            if phone.is_coexistence or (
                phone.registration_status == PhoneNumber.RegistrationStatus.REGISTERED
            ):
                continue
            if waba.onboarding_status != statuses.REGISTERING:
                _update(waba, onboarding_status=statuses.REGISTERING)
            services.register_phone_number(phone, client)

        for phone in phones:
            services.sync_phone_number(phone, client)

        _update(
            waba,
            status=WhatsAppBusinessAccount.Status.ACTIVE,
            onboarding_status=statuses.COMPLETED,
            last_error="",
        )
    except GraphAPIError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc, countdown=backoff_seconds(self.request.retries, exc)
            ) from None
        logger.warning(
            "WhatsApp onboarding failed for WABA %s: %s", waba.waba_id, type(exc).__name__
        )
        _update(waba, onboarding_status=statuses.FAILED, last_error=exc.message or str(type(exc)))


@shared_task(bind=True, name="whatsapp.refresh_phone_number", max_retries=3)
def refresh_phone_number(self, phone_pk: str) -> None:
    phone = PhoneNumber.objects.select_related("waba").filter(pk=phone_pk).first()
    if phone is None:
        return
    waba = phone.waba
    if waba.status == WhatsAppBusinessAccount.Status.DISCONNECTED or not waba.access_token:
        return
    try:
        services.sync_phone_number(phone)
    except TokenInvalidError:
        services.mark_reconnect_required(waba)
    except GraphAPIError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc, countdown=backoff_seconds(self.request.retries, exc)
            ) from None
        _update(phone, last_error=exc.message)


@shared_task(bind=True, name="whatsapp.refresh_all_phone_numbers")
def refresh_all_phone_numbers(self) -> int:
    phone_pks = PhoneNumber.objects.filter(
        waba__status__in=[
            WhatsAppBusinessAccount.Status.ACTIVE,
            WhatsAppBusinessAccount.Status.RESTRICTED,
        ]
    ).values_list("pk", flat=True)
    count = 0
    for phone_pk in phone_pks.iterator():
        refresh_phone_number.delay(str(phone_pk))
        count += 1
    return count
