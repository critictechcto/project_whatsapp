"""Razorpay API access (subscriptions) and signature checks.

Always go through :func:`get_razorpay_client`; tests install :class:`FakeRazorpayClient` with
:func:`override_razorpay_client` and never reach the network. Never log key secrets, webhook
secrets or signatures.

Razorpay plans (``RAZORPAY_PLAN_IDS``) must be created with GST-inclusive amounts: Razorpay charges
the plan amount as is, while UpChatz prices exclude GST and invoices add it on top.
"""

import hashlib
import hmac
import itertools
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Protocol

import httpx
from django.conf import settings

JSON = dict[str, Any]

API_BASE_URL = "https://api.razorpay.com/v1"
# Billing cycles before a Razorpay subscription completes (10 years either way).
TOTAL_COUNT = {"monthly": 120, "annual": 10}

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


class RazorpayNotConfigured(RazorpayError):
    """API keys or plan ids are missing from settings."""


class RazorpayClient(Protocol):
    def create_subscription(
        self, *, plan_id: str, total_count: int, notes: Mapping[str, str]
    ) -> JSON: ...

    def fetch_subscription(self, subscription_id: str) -> JSON: ...

    def cancel_subscription(self, subscription_id: str, *, at_cycle_end: bool) -> JSON: ...


def _checked_id(subscription_id: str) -> str:
    if not isinstance(subscription_id, str) or not _ID_RE.fullmatch(subscription_id):
        raise RazorpayError("Invalid Razorpay subscription id.")
    return subscription_id


class HttpRazorpayClient:
    """Thin httpx client with basic auth (key id + key secret)."""

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

    def create_subscription(
        self, *, plan_id: str, total_count: int, notes: Mapping[str, str]
    ) -> JSON:
        body = {
            "plan_id": plan_id,
            "total_count": total_count,
            "quantity": 1,
            "customer_notify": 1,
            "notes": dict(notes),
        }
        return self._request("POST", "/subscriptions", json=body)

    def fetch_subscription(self, subscription_id: str) -> JSON:
        return self._request("GET", f"/subscriptions/{_checked_id(subscription_id)}")

    def cancel_subscription(self, subscription_id: str, *, at_cycle_end: bool) -> JSON:
        return self._request(
            "POST",
            f"/subscriptions/{_checked_id(subscription_id)}/cancel",
            json={"cancel_at_cycle_end": 1 if at_cycle_end else 0},
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, *, json: JSON | None = None) -> JSON:
        try:
            response = self._client.request(method, path, json=json)
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


class FakeRazorpayClient:
    """In-memory Razorpay for tests. ``calls`` records every call; set ``fail_with`` to raise."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, JSON] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_with: RazorpayError | None = None
        self._ids = itertools.count(1)

    def create_subscription(
        self, *, plan_id: str, total_count: int, notes: Mapping[str, str]
    ) -> JSON:
        self._record("create_subscription", plan_id=plan_id, total_count=total_count, notes=notes)
        subscription_id = f"sub_fake{next(self._ids):06d}"
        entity = {
            "id": subscription_id,
            "entity": "subscription",
            "plan_id": plan_id,
            "status": "created",
            "total_count": total_count,
            "paid_count": 0,
            "notes": dict(notes),
            "short_url": f"https://rzp.io/i/{subscription_id}",
        }
        self.subscriptions[subscription_id] = entity
        return dict(entity)

    def fetch_subscription(self, subscription_id: str) -> JSON:
        self._record("fetch_subscription", subscription_id=subscription_id)
        return dict(self._get(subscription_id))

    def cancel_subscription(self, subscription_id: str, *, at_cycle_end: bool) -> JSON:
        self._record(
            "cancel_subscription", subscription_id=subscription_id, at_cycle_end=at_cycle_end
        )
        entity = self._get(subscription_id)
        if not at_cycle_end:
            entity["status"] = "cancelled"
        return dict(entity)

    def calls_to(self, name: str) -> list[dict]:
        return [kwargs for call, kwargs in self.calls if call == name]

    def _get(self, subscription_id: str) -> JSON:
        entity = self.subscriptions.get(subscription_id)
        if entity is None:
            raise RazorpayError(
                "The id provided does not exist", status_code=400, code="BAD_REQUEST_ERROR"
            )
        return entity

    def _record(self, name: str, **kwargs) -> None:
        self.calls.append((name, kwargs))
        if self.fail_with is not None:
            raise self.fail_with


_override: RazorpayClient | None = None


def get_razorpay_client() -> RazorpayClient:
    if _override is not None:
        return _override
    return HttpRazorpayClient(
        key_id=settings.RAZORPAY_KEY_ID, key_secret=settings.RAZORPAY_KEY_SECRET
    )


@contextmanager
def override_razorpay_client(client: RazorpayClient) -> Iterator[RazorpayClient]:
    global _override
    previous = _override
    _override = client
    try:
        yield client
    finally:
        _override = previous


# --- Plans ----------------------------------------------------------------------------------


def plan_id_for(plan_slug: str, interval: str) -> str:
    """Razorpay plan id for a plan and interval, from ``RAZORPAY_PLAN_IDS``."""
    plan_id = (settings.RAZORPAY_PLAN_IDS or {}).get(plan_slug, {}).get(interval)
    if not plan_id:
        raise RazorpayNotConfigured(f"No Razorpay plan id configured for {plan_slug}/{interval}.")
    return plan_id


def plan_for_razorpay_plan_id(razorpay_plan_id: object) -> tuple[str, str] | None:
    """``(plan slug, interval)`` for a Razorpay plan id, or None when it isn't configured."""
    if not isinstance(razorpay_plan_id, str) or not razorpay_plan_id:
        return None
    for slug, intervals in (settings.RAZORPAY_PLAN_IDS or {}).items():
        for interval, plan_id in (intervals or {}).items():
            if plan_id == razorpay_plan_id:
                return slug, interval
    return None


# --- Signatures -----------------------------------------------------------------------------


def _hmac_sha256_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _matches(expected_hex: str, provided: object) -> bool:
    if not isinstance(provided, str) or not provided:
        return False
    return hmac.compare_digest(expected_hex.encode(), provided.strip().lower().encode())


def checkout_signature_is_valid(
    *, payment_id: str, subscription_id: str, signature: str, secret: str
) -> bool:
    """Checkout (subscription mode) signs ``razorpay_payment_id|razorpay_subscription_id``."""
    if not (secret and payment_id and subscription_id):
        return False
    expected = _hmac_sha256_hex(secret, f"{payment_id}|{subscription_id}".encode())
    return _matches(expected, signature)


def webhook_signature_is_valid(body: bytes, signature: str | None, secret: str) -> bool:
    """``X-Razorpay-Signature`` is the hex HMAC-SHA256 of the raw body with the webhook secret."""
    if not secret:
        return False
    return _matches(_hmac_sha256_hex(secret, body), signature)
