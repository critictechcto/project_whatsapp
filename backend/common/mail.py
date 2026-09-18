"""Transactional email: render ``emails/<template>.{subject.txt,txt,html}`` and send it.

Celery tasks send through :func:`send_or_retry`, which retries only failures worth retrying
(Resend timeouts, 429 and 5xx; SMTP connection drops and 4xx replies).
"""

import smtplib

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .mail_backends import IDEMPOTENCY_HEADER, EmailSendError

BRAND = "UpChatz"
EMAIL_MAX_RETRIES = 5
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 30 * 60


def base_context() -> dict:
    return {
        "brand": BRAND,
        "site_url": settings.SITE_URL.rstrip("/"),
        "support_email": settings.EMAIL_REPLY_TO,
    }


def render_email(template: str, context: dict) -> tuple[str, str, str]:
    """Subject (one line), plain text and HTML for ``emails/<template>``."""
    context = {**base_context(), **context}
    subject = render_to_string(f"emails/{template}.subject.txt", context)
    subject = " ".join(subject.split())
    text = render_to_string(f"emails/{template}.txt", context).strip() + "\n"
    html = render_to_string(f"emails/{template}.html", context)
    return subject, text, html


def send_templated_email(
    *, to: str, template: str, context: dict, idempotency_key: str | None = None
) -> None:
    subject, text, html = render_email(template, context)
    headers = {IDEMPOTENCY_HEADER: idempotency_key} if idempotency_key else None
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        reply_to=[settings.EMAIL_REPLY_TO],
        headers=headers,
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)


def is_retryable_email_error(exc: BaseException) -> bool:
    if isinstance(exc, EmailSendError):
        return exc.retryable
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    return isinstance(
        exc,
        smtplib.SMTPServerDisconnected | smtplib.SMTPConnectError | TimeoutError | ConnectionError,
    )


def retry_countdown(retries: int) -> int:
    return min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * 2**retries)


def send_or_retry(task, *, retry_kwargs: dict | None = None, **email) -> None:
    """Send from inside a bound Celery task; retry with exponential backoff when worthwhile.

    ``retry_kwargs`` replaces the task's arguments on retry (all passed by keyword), e.g. to
    resend the same token and keep the idempotency key stable.
    """
    try:
        send_templated_email(**email)
    except Exception as exc:
        if not is_retryable_email_error(exc):
            raise
        options = {"args": (), "kwargs": retry_kwargs} if retry_kwargs is not None else {}
        raise task.retry(
            exc=exc,
            countdown=retry_countdown(task.request.retries),
            max_retries=EMAIL_MAX_RETRIES,
            **options,
        ) from exc
