"""Razorpay provider: request building, doc-shaped responses, errors and signatures."""

import base64
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from django.utils import timezone

from apps.payments.exceptions import (
    PaymentAccountInvalid,
    PaymentAccountMissing,
    PaymentProviderError,
)
from apps.payments.providers import (
    CANCELLED,
    CREATED,
    PAID,
    InvalidWebhookSignature,
    LinkRequest,
    RazorpayProvider,
)
from common.razorpay import hmac_sha256_hex

KEY_ID = "rzp_test_Abc123"
KEY_SECRET = "rzp-key-secret-do-not-leak"
WEBHOOK_SECRET = "rzp-webhook-secret-do-not-leak"

# Shapes from https://razorpay.com/docs/api/payments/payment-links/create-standard/ and
# https://razorpay.com/docs/api/payments/payment-links/fetch-id-standard/
CREATED_LINK = {
    "id": "plink_ExjpAUN3gVHrPJ",
    "amount": 49800,
    "currency": "INR",
    "status": "created",
    "short_url": "https://rzp.io/i/nxrHnLJ",
    "amount_paid": 0,
    "expire_by": 1691097057,
    "accept_partial": False,
    "reference_id": "SS-1001-1",
    "description": "Order SS-1001",
    "customer": {"name": "Asha Verma", "contact": "+919876543210"},
    "notify": {"sms": False, "email": False},
    "reminder_enable": False,
    "callback_url": "https://api.testserver/pay/return/x/",
    "callback_method": "get",
    "notes": {"order_id": "o1"},
    "payments": None,
    "reminders": [],
    "created_at": 1591097057,
    "updated_at": 1591097057,
    "cancelled_at": 0,
    "expired_at": 0,
    "user_id": "",
}
PAID_LINK = {
    "accept_partial": False,
    "amount": 10000,
    "amount_paid": 10000,
    "cancelled_at": 0,
    "created_at": 1661852539,
    "currency": "INR",
    "customer": [],
    "description": "Grocery",
    "expire_by": 0,
    "expired_at": 0,
    "id": "plink_KBnb7I424Rc1R9",
    "notes": None,
    "notify": {"email": False, "sms": False},
    "order_id": "order_KBneAVhT2zbzsU",
    "payments": [
        {
            "amount": 10000,
            "created_at": 1661852741,
            "method": "card",
            "payment_id": "pay_KBnebtRrhTEatJ",
            "status": "captured",
        }
    ],
    "reference_id": "111",
    "reminder_enable": False,
    "reminders": [],
    "short_url": "https://rzp.io/i/alaBxs0i",
    "status": "paid",
    "updated_at": 1661852741,
    "upi_link": False,
    "user_id": "HD1JAKCCPGDfRx",
}


def provider(handler, **kwargs) -> RazorpayProvider:
    options = {"key_id": KEY_ID, "key_secret": KEY_SECRET, "webhook_secret": WEBHOOK_SECRET}
    options.update(kwargs)
    return RazorpayProvider(**options, transport=httpx.MockTransport(handler))


def link_request(**overrides) -> LinkRequest:
    values = {
        "reference_id": "SS-1001-1",
        "amount_paise": 49800,
        "currency": "INR",
        "description": "Order SS-1001",
        "customer_name": "Asha Verma",
        "customer_phone_e164": "+919876543210",
        "expire_by": timezone.now() + timedelta(minutes=30),
        "return_url": "https://api.testserver/pay/return/abc/",
        "notes": {"workspace_id": "w1", "order_id": "o1"},
    }
    values.update(overrides)
    return LinkRequest(**values)


def error(status: int, description: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": "BAD_REQUEST_ERROR", "description": description}}
    )


def test_create_link_builds_the_documented_request():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=CREATED_LINK)

    request = link_request()
    state = provider(handler).create_link(request)

    sent = seen[0]
    assert sent.method == "POST"
    assert str(sent.url) == "https://api.razorpay.com/v1/payment_links"
    expected_auth = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
    assert sent.headers["Authorization"] == f"Basic {expected_auth}"
    body = json.loads(sent.content)
    assert body == {
        "amount": 49800,
        "currency": "INR",
        "accept_partial": False,
        "expire_by": int(request.expire_by.timestamp()),
        "reference_id": "SS-1001-1",
        "description": "Order SS-1001",
        "customer": {"name": "Asha Verma", "contact": "+919876543210"},
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {"workspace_id": "w1", "order_id": "o1"},
        "callback_url": "https://api.testserver/pay/return/abc/",
        "callback_method": "get",
    }
    assert state.provider_link_id == "plink_ExjpAUN3gVHrPJ"
    assert state.short_url == "https://rzp.io/i/nxrHnLJ"
    assert state.status == CREATED
    assert state.amount_paise == 49800
    assert state.currency == "INR"
    assert state.expires_at == datetime.fromtimestamp(1691097057, tz=UTC)


def test_create_link_keeps_expire_by_at_least_15_minutes_ahead():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=CREATED_LINK)

    provider(handler).create_link(link_request(expire_by=timezone.now() + timedelta(minutes=5)))

    assert seen[0]["expire_by"] >= int((timezone.now() + timedelta(minutes=15)).timestamp())


def test_create_link_is_idempotent_on_reference_id():
    def handler(request):
        if request.method == "POST":
            return error(400, "Reference id already exists")
        assert request.url.params["reference_id"] == "SS-1001-1"
        return httpx.Response(200, json={"payment_links": [CREATED_LINK]})

    state = provider(handler).create_link(link_request())

    assert state.provider_link_id == "plink_ExjpAUN3gVHrPJ"


def test_fetch_paid_link_parses_payment():
    def handler(request):
        assert request.url.path == "/v1/payment_links/plink_KBnb7I424Rc1R9"
        return httpx.Response(200, json=PAID_LINK)

    state = provider(handler).fetch_link("plink_KBnb7I424Rc1R9")

    assert state.status == PAID
    assert state.amount_paid_paise == 10000
    assert state.provider_payment_id == "pay_KBnebtRrhTEatJ"
    assert state.paid_at == datetime.fromtimestamp(1661852741, tz=UTC)
    assert state.raw["id"] == "plink_KBnb7I424Rc1R9"


def test_fetch_rejects_unsafe_ids_without_a_call():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    with pytest.raises(PaymentProviderError):
        provider(handler).fetch_link("../payments")


def test_cancel_link_and_cancel_of_a_paid_link():
    def cancel_ok(request):
        return httpx.Response(200, json={**CREATED_LINK, "status": "cancelled"})

    assert provider(cancel_ok).cancel_link("plink_ExjpAUN3gVHrPJ").status == CANCELLED

    def cancel_paid(request):
        if request.method == "POST":
            assert request.url.path.endswith("/cancel")
            return error(400, "Payment link cannot be cancelled as it is already paid")
        return httpx.Response(200, json=PAID_LINK)

    assert provider(cancel_paid).cancel_link("plink_KBnb7I424Rc1R9").status == PAID


@pytest.mark.parametrize(
    ("response", "status_code", "retryable"),
    [
        (lambda r: error(500, "Server error"), 500, True),
        (lambda r: error(429, "Too many requests"), 429, True),
        (lambda r: error(400, "The amount must be at least INR 1.00"), 400, False),
    ],
)
def test_errors_are_mapped(response, status_code, retryable):
    with pytest.raises(PaymentProviderError) as caught:
        provider(response).fetch_link("plink_ExjpAUN3gVHrPJ")

    assert caught.value.provider == "razorpay"
    assert caught.value.status_code == status_code
    assert caught.value.retryable is retryable


def test_network_errors_are_retryable():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(PaymentProviderError) as caught:
        provider(handler).fetch_link("plink_ExjpAUN3gVHrPJ")

    assert caught.value.retryable is True
    assert caught.value.status_code is None


def test_verify_credentials():
    seen = []

    def ok(request):
        seen.append(request)
        return httpx.Response(200, json={"entity": "collection", "count": 0, "items": []})

    provider(ok).verify_credentials()
    assert seen[0].url.path == "/v1/payments"
    assert seen[0].url.params["count"] == "1"

    with pytest.raises(PaymentAccountInvalid):
        provider(lambda r: error(401, "The api key provided is invalid")).verify_credentials()

    with pytest.raises(PaymentProviderError):
        provider(lambda r: error(503, "Unavailable")).verify_credentials()

    with pytest.raises(PaymentAccountMissing):
        provider(ok, key_secret="").verify_credentials()


def webhook(event: str, entity: dict, payment: dict | None = None) -> bytes:
    payload = {"payment_link": {"entity": entity}}
    if payment:
        payload["payment"] = {"entity": payment}
    return json.dumps(
        {
            "entity": "event",
            "account_id": "acc_BFQ7uQEaa7j2z7",
            "event": event,
            "contains": list(payload),
            "payload": payload,
            "created_at": 1661852745,
        }
    ).encode()


def test_webhook_signature_and_parsing():
    body = webhook(
        "payment_link.paid",
        {**CREATED_LINK, "status": "paid", "amount_paid": 49800},
        {"id": "pay_Kxyz", "amount": 49800, "status": "captured", "created_at": 1661852741},
    )
    headers = {
        "X-Razorpay-Signature": hmac_sha256_hex(WEBHOOK_SECRET, body),
        "X-Razorpay-Event-Id": "KDVKMfQPi4YgN1",
    }

    [update] = provider(lambda r: None).parse_webhook(headers, body)

    assert update.event_id == "KDVKMfQPi4YgN1"
    assert update.event_type == "payment_link.paid"
    assert update.provider_link_id == "plink_ExjpAUN3gVHrPJ"
    assert update.state.status == PAID
    assert update.state.amount_paid_paise == 49800
    assert update.state.provider_payment_id == "pay_Kxyz"


def test_webhook_rejects_bad_signatures():
    body = webhook("payment_link.expired", {**CREATED_LINK, "status": "expired"})
    with pytest.raises(InvalidWebhookSignature):
        provider(lambda r: None).parse_webhook({"X-Razorpay-Signature": "00" * 32}, body)
    with pytest.raises(InvalidWebhookSignature):
        provider(lambda r: None).parse_webhook({}, body)
    signed = {"X-Razorpay-Signature": hmac_sha256_hex(WEBHOOK_SECRET, body)}
    with pytest.raises(InvalidWebhookSignature):
        provider(lambda r: None, webhook_secret="").parse_webhook(signed, body)


def test_webhook_ignores_other_events_and_hashes_missing_event_ids():
    other = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    signed = {"X-Razorpay-Signature": hmac_sha256_hex(WEBHOOK_SECRET, other)}
    assert provider(lambda r: None).parse_webhook(signed, other) == []

    body = webhook("payment_link.cancelled", {**CREATED_LINK, "status": "cancelled"})
    signed = {"x-razorpay-signature": hmac_sha256_hex(WEBHOOK_SECRET, body)}
    [update] = provider(lambda r: None).parse_webhook(signed, body)
    assert update.event_id.startswith("sha256:")
    assert update.state.status == CANCELLED


def test_callback_signature():
    params = {
        "razorpay_payment_id": "pay_Kxyz",
        "razorpay_payment_link_id": "plink_ExjpAUN3gVHrPJ",
        "razorpay_payment_link_reference_id": "SS-1001-1",
        "razorpay_payment_link_status": "paid",
    }
    message = b"plink_ExjpAUN3gVHrPJ|SS-1001-1|paid|pay_Kxyz"
    rzp = provider(lambda r: None)

    assert rzp.callback_signature_is_valid(
        {**params, "razorpay_signature": hmac_sha256_hex(KEY_SECRET, message)}
    )
    assert not rzp.callback_signature_is_valid({**params, "razorpay_signature": "bad"})
    assert not rzp.callback_signature_is_valid(params)


def test_secrets_never_appear_in_repr_or_errors():
    def handler(request):
        return error(401, "Authentication failed")

    rzp = provider(handler)
    with pytest.raises(PaymentProviderError) as caught:
        rzp.fetch_link("plink_ExjpAUN3gVHrPJ")

    assert KEY_SECRET not in repr(rzp)
    assert KEY_SECRET not in str(caught.value)
