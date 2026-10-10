"""common.cashfree: key selection, transport and webhook signatures. No network."""

import base64
import hashlib
import hmac
import json

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from common.cashfree import (
    API_VERSION,
    CashfreeError,
    CashfreeNotConfigured,
    CashfreeTransport,
    cashfree_phone,
    credentials_for,
    webhook_signature_is_valid,
)

ENV = {
    "TEST_CASHFREE_API_APP_ID": "TEST-app",
    "TEST_CASHFREE_API_SECRET": "cfsk_test_secret",
    "CASHFREE_API_APP_ID": "LIVE-app",
    "CASHFREE_API_SECRET": "cfsk_live_secret",
}


def test_sandbox_uses_the_test_keys():
    assert credentials_for("sandbox", ENV.get) == ("TEST-app", "cfsk_test_secret")


def test_production_uses_the_live_keys():
    assert credentials_for("production", ENV.get) == ("LIVE-app", "cfsk_live_secret")


def test_missing_keys_are_blank():
    assert credentials_for("production", {}.get) == ("", "")


def test_unknown_environment_is_rejected():
    with pytest.raises(ImproperlyConfigured):
        credentials_for("live", ENV.get)


def test_settings_default_to_cashfree_sandbox(settings):
    # config.settings.test pins the provider and keys; base.py defaults match.
    assert (settings.BILLING_PROVIDER, settings.CASHFREE_ENV) == ("cashfree", "sandbox")
    assert settings.BILLING_CASHFREE_APP_ID and settings.BILLING_CASHFREE_SECRET


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_webhook_signature():
    body = b'{"type":"PAYMENT_SUCCESS_WEBHOOK"}'
    good = _signature("secret", "1760078407", body)

    assert webhook_signature_is_valid(body, "1760078407", good, "secret")
    assert not webhook_signature_is_valid(body, "1760078408", good, "secret")
    assert not webhook_signature_is_valid(body + b" ", "1760078407", good, "secret")
    assert not webhook_signature_is_valid(body, "1760078407", good, "other")
    assert not webhook_signature_is_valid(body, None, good, "secret")
    assert not webhook_signature_is_valid(body, "1760078407", None, "secret")
    assert not webhook_signature_is_valid(body, "1760078407", good, "")


@pytest.mark.parametrize(
    ("e164", "expected"), [("+919876543210", "9876543210"), ("+14155552671", "14155552671")]
)
def test_cashfree_phone(e164, expected):
    assert cashfree_phone(e164) == expected


def _transport(handler) -> CashfreeTransport:
    return CashfreeTransport(
        "app-id", "cfsk-secret", "sandbox", transport=httpx.MockTransport(handler)
    )


def test_transport_sends_auth_headers_and_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"order_id": "upc_1"})

    data = _transport(handler).request(
        "POST", "/orders", json={"order_id": "upc_1"}, headers={"x-idempotency-key": "upc_1"}
    )

    assert data == {"order_id": "upc_1"}
    assert seen["url"] == "https://sandbox.cashfree.com/pg/orders"
    assert seen["headers"]["x-client-id"] == "app-id"
    assert seen["headers"]["x-client-secret"] == "cfsk-secret"
    assert seen["headers"]["x-api-version"] == API_VERSION
    assert seen["headers"]["x-idempotency-key"] == "upc_1"
    assert seen["body"] == {"order_id": "upc_1"}


@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (401, False), (429, True), (502, True)]
)
def test_transport_maps_errors(status, retryable):
    transport = _transport(lambda request: httpx.Response(status, json={"message": "nope"}))

    with pytest.raises(CashfreeError) as excinfo:
        transport.request("GET", "/orders/upc_1")

    assert (excinfo.value.status_code, excinfo.value.retryable) == (status, retryable)
    assert str(excinfo.value) == "nope"


def test_transport_network_errors_are_retryable():
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(CashfreeError) as excinfo:
        _transport(handler).request("GET", "/orders/upc_1")

    assert excinfo.value.retryable and excinfo.value.status_code is None


def test_transport_needs_keys_and_hides_the_secret():
    with pytest.raises(CashfreeNotConfigured):
        CashfreeTransport("", "", "sandbox")

    assert "cfsk-secret" not in repr(_transport(lambda request: httpx.Response(200, json={})))
