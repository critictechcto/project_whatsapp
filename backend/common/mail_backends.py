"""Email backends. ``ResendEmailBackend`` sends through Resend's HTTP API.

Production uses HTTPS instead of SMTP because hosting providers (DigitalOcean among them) may
block outbound SMTP ports. Select it with ``EMAIL_BACKEND = "common.mail_backends.
ResendEmailBackend"`` and set ``RESEND_API_KEY``.
"""

import logging

import httpx
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
IDEMPOTENCY_HEADER = "Idempotency-Key"
DEFAULT_TIMEOUT = 15.0

# Tests swap in an ``httpx.MockTransport``; None = httpx's real network transport.
_transport: httpx.BaseTransport | None = None


class EmailSendError(Exception):
    """Sending failed. ``retryable`` is True for timeouts, transport errors, 429 and 5xx."""

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code

    def __reduce__(self):
        # Keyword-only arguments: tell pickle (Celery results, retries) how to rebuild it.
        return (_rebuild_email_send_error, (str(self), self.retryable, self.status_code))


def _rebuild_email_send_error(message: str, retryable: bool, status_code: int | None):
    return EmailSendError(message, retryable=retryable, status_code=status_code)


class ResendEmailBackend(BaseEmailBackend):
    def __init__(
        self,
        fail_silently: bool = False,
        *,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
        **kwargs,
    ):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = api_key if api_key is not None else settings.RESEND_API_KEY
        self.timeout = (
            timeout if timeout is not None else getattr(settings, "RESEND_TIMEOUT", DEFAULT_TIMEOUT)
        )
        self.transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            transport=self.transport or _transport,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def send_messages(self, email_messages) -> int:
        messages = [m for m in email_messages or [] if m.recipients()]
        if not messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise EmailSendError("RESEND_API_KEY is not set.", retryable=False)

        sent = 0
        with self._client() as client:
            for message in messages:
                try:
                    self._send(client, message)
                except EmailSendError:
                    if self.fail_silently:
                        return sent
                    raise
                sent += 1
        return sent

    def _send(self, client: httpx.Client, message: EmailMessage) -> None:
        payload, idempotency_key = build_payload(message)
        request_headers = {IDEMPOTENCY_HEADER: idempotency_key} if idempotency_key else {}
        try:
            response = client.post(RESEND_API_URL, json=payload, headers=request_headers)
        except httpx.TimeoutException as exc:
            logger.warning("Resend request timed out.")
            raise EmailSendError("Resend request timed out.", retryable=True) from exc
        except httpx.HTTPError as exc:
            logger.warning("Resend transport error: %s", type(exc).__name__)
            raise EmailSendError("Could not reach Resend.", retryable=True) from exc

        if response.is_success:
            return
        status = response.status_code
        name, detail = _error_fields(response)
        logger.warning(
            "Resend rejected an email: status=%s name=%s message=%s", status, name, detail
        )
        retryable = status == 429 or status >= 500
        raise EmailSendError(
            f"Resend returned {status}: {name or 'error'}", retryable=retryable, status_code=status
        )


def build_payload(message: EmailMessage) -> tuple[dict, str | None]:
    """Resend JSON body for ``message`` and its idempotency key (sent as an HTTP header)."""
    extra_headers = dict(message.extra_headers or {})
    idempotency_key = None
    for key in list(extra_headers):
        if key.lower() == IDEMPOTENCY_HEADER.lower():
            idempotency_key = str(extra_headers.pop(key))

    payload: dict = {
        "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
        "to": list(message.to),
        "subject": message.subject,
        "text": message.body,
    }
    if message.cc:
        payload["cc"] = list(message.cc)
    if message.bcc:
        payload["bcc"] = list(message.bcc)
    if message.reply_to:
        payload["reply_to"] = list(message.reply_to)
    for alternative in getattr(message, "alternatives", None) or []:
        content, mimetype = alternative[0], alternative[1]
        if mimetype == "text/html":
            payload["html"] = content
            break
    if extra_headers:
        payload["headers"] = {key: str(value) for key, value in extra_headers.items()}
    return payload, idempotency_key


def _error_fields(response: httpx.Response) -> tuple[str, str]:
    try:
        body = response.json()
    except ValueError:
        return "", ""
    if not isinstance(body, dict):
        return "", ""
    return str(body.get("name", ""))[:100], str(body.get("message", ""))[:300]
