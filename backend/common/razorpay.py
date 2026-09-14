"""Shared Razorpay transport and signature checks.

Used by ``apps.billing`` (UpChatz's own subscriptions, platform keys) and ``apps.payments``
(payment links on each seller's own Razorpay account, per-workspace keys). Never log key
secrets, webhook secrets or signatures.
"""

import hashlib
import hmac
import re
from typing import Any

import httpx
from django.conf import settings

JSON = dict[str, Any]

API_BASE_URL = "https://api.razorpay.com/v1"

_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class RazorpayError(Exception):
    """A failed Razorpay call. ``status_code`` is None for network errors."""

    def __init__(self, message: str, *, status_code: int | None = None, code: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code

    @property
    def retryable(self) -> bool:
        return self.status_code is None or self.status_code == 429 or self.status_code >= 500

    @property
    def is_auth_error(self) -> bool:
        """Razorpay rejected the key id or secret."""
        return self.status_code == 401


class RazorpayNotConfigured(RazorpayError):
    """API keys (or other required settings) are missing."""


def checked_id(value: str, *, label: str = "Razorpay id") -> str:
    """``value`` if it is a safe Razorpay entity id for a URL path, else ``RazorpayError``."""
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise RazorpayError(f"Invalid {label}.")
    return value


class RazorpayTransport:
    """Thin httpx client with basic auth (key id + key secret) and Razorpay error mapping."""

    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        base_url: str = API_BASE_URL,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not key_id or not key_secret:
            raise RazorpayNotConfigured("Razorpay API keys are not configured.")
        self._client = httpx.Client(
            base_url=base_url,
            auth=(key_id, key_secret),
            timeout=settings.RAZORPAY_TIMEOUT if timeout is None else timeout,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: JSON | None = None,
        params: dict[str, Any] | None = None,
    ) -> JSON:
        try:
            response = self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise RazorpayError(f"Razorpay request failed ({type(exc).__name__}).") from exc
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.is_error:
            error = data.get("error") if isinstance(data, dict) else None
            error = error if isinstance(error, dict) else {}
            raise RazorpayError(
                str(error.get("description") or f"Razorpay returned HTTP {response.status_code}."),
                status_code=response.status_code,
                code=str(error.get("code") or ""),
            )
        if not isinstance(data, dict):
            raise RazorpayError(
                "Razorpay returned an unexpected response.", status_code=response.status_code
            )
        return data

    def close(self) -> None:
        self._client.close()


# --- Signatures -----------------------------------------------------------------------------


def hmac_sha256_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signature_matches(expected_hex: str, provided: object) -> bool:
    if not isinstance(provided, str) or not provided:
        return False
    return hmac.compare_digest(expected_hex.encode(), provided.strip().lower().encode())


def webhook_signature_is_valid(body: bytes, signature: str | None, secret: str) -> bool:
    """``X-Razorpay-Signature`` is the hex HMAC-SHA256 of the raw body with the webhook secret."""
    if not secret:
        return False
    return signature_matches(hmac_sha256_hex(secret, body), signature)
