"""Shared Cashfree Payment Gateway (PG) transport and webhook signature check.

Used by ``apps.billing`` (UpChatz's own prepaid plans, platform keys from settings). The per-seller
payment links in ``apps.payments`` keep their own transport. Checked against the official docs
(September 2026):

- Base URLs: ``sandbox`` → ``https://sandbox.cashfree.com/pg``, ``production`` →
  ``https://api.cashfree.com/pg``. Headers ``x-client-id``, ``x-client-secret`` and
  ``x-api-version`` (pinned in :data:`API_VERSION`); errors carry ``{"message", "code", "type"}``.
- Webhooks (https://www.cashfree.com/docs/payments/online/webhooks/signature-verification):
  ``x-webhook-signature`` = base64(HMAC-SHA256(secret key, ``x-webhook-timestamp`` + raw body)).

Never log the secret key, the ``x-client-secret`` header or signatures.
"""

import base64
import hashlib
import hmac
import re
from collections.abc import Callable
from typing import Any

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

JSON = dict[str, Any]

API_VERSION = "2026-01-01"
BASE_URLS = {
    "sandbox": "https://sandbox.cashfree.com/pg",
    "production": "https://api.cashfree.com/pg",
}
ENVIRONMENTS = tuple(BASE_URLS)
DEFAULT_TIMEOUT = 20.0
# Env var names holding the platform keys, by CASHFREE_ENV.
CREDENTIAL_ENV_VARS = {
    "sandbox": ("TEST_CASHFREE_API_APP_ID", "TEST_CASHFREE_API_SECRET"),
    "production": ("CASHFREE_API_APP_ID", "CASHFREE_API_SECRET"),
}

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CashfreeError(Exception):
    """A failed Cashfree call. ``status_code`` is None for network errors."""

    def __init__(
        self, message: str, *, status_code: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class CashfreeNotConfigured(CashfreeError):
    """The App ID or secret key is missing."""


def checked_id(value: str, *, label: str = "Cashfree id") -> str:
    """``value`` if it is safe in a URL path, else ``CashfreeError``."""
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise CashfreeError(f"Invalid {label}.")
    return value


def cashfree_phone(phone_e164: str) -> str:
    """Cashfree's ``customer_phone``: 10 digits for Indian numbers, digits otherwise."""
    digits = re.sub(r"\D", "", phone_e164 or "")
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    return digits


def credentials_for(cashfree_env: str, getenv: Callable[[str], str]) -> tuple[str, str]:
    """``(app id, secret)`` for ``CASHFREE_ENV``: the ``TEST_*`` keys in sandbox, the live keys
    in production. Missing keys are ``""``; an unknown environment is ``ImproperlyConfigured``."""
    names = CREDENTIAL_ENV_VARS.get(cashfree_env)
    if names is None:
        raise ImproperlyConfigured(
            f"CASHFREE_ENV must be one of {', '.join(ENVIRONMENTS)}, not {cashfree_env!r}."
        )
    app_id, secret = (str(getenv(name) or "").strip() for name in names)
    return app_id, secret


class CashfreeTransport:
    """Thin httpx client with Cashfree auth headers and error mapping (429/5xx/network errors are
    retryable)."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        mode: str,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise CashfreeNotConfigured("Cashfree API keys are not configured.")
        if mode not in BASE_URLS:
            raise CashfreeNotConfigured(f"Unknown Cashfree environment {mode!r}.")
        self.mode = mode
        self._client = httpx.Client(
            base_url=BASE_URLS[mode],
            timeout=getattr(settings, "CASHFREE_TIMEOUT", DEFAULT_TIMEOUT)
            if timeout is None
            else timeout,
            transport=transport,
            headers={
                "x-client-id": client_id,
                "x-client-secret": client_secret,
                "x-api-version": API_VERSION,
                "Accept": "application/json",
            },
        )

    def __repr__(self) -> str:  # never show the secret
        return f"{type(self).__name__}(mode={self.mode!r})"

    def request(
        self,
        method: str,
        path: str,
        json: JSON | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise CashfreeError(
                f"Cashfree request failed ({type(exc).__name__}).", retryable=True
            ) from None
        try:
            data = response.json()
        except ValueError:
            data = None
        status = response.status_code
        if response.is_error:
            message = data.get("message") if isinstance(data, dict) else None
            raise CashfreeError(
                str(message or f"Cashfree returned HTTP {status}.")[:300],
                status_code=status,
                retryable=status == 429 or status >= 500,
            )
        if data is None:
            raise CashfreeError(
                "Cashfree returned an unexpected response.", status_code=status, retryable=True
            )
        return data

    def close(self) -> None:
        self._client.close()


def webhook_signature_is_valid(
    raw_body: bytes, timestamp: str | None, signature: str | None, secret: str
) -> bool:
    """``x-webhook-signature`` is base64(HMAC-SHA256(secret, ``x-webhook-timestamp`` + body))."""
    if not (secret and timestamp and signature) or not isinstance(raw_body, bytes):
        return False
    digest = hmac.new(secret.encode(), timestamp.encode() + raw_body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest), signature.strip().encode())
