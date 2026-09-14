"""Cashfree provider: request building, doc-shaped responses, errors and webhook signatures."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

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
    EXPIRED,
    PAID,
    PARTIALLY_PAID,
    CashfreeProvider,
    InvalidWebhookSignature,
    LinkRequest,
)
from apps.payments.providers.base import paise_to_rupees, rupees_to_paise
from apps.payments.providers.cashfree import API_VERSION, cashfree_phone

CLIENT_ID = "TEST10123456789"
CLIENT_SECRET = "cfsk_ma_test_do_not_leak"

# Shapes from https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/create
ACTIVE_LINK = {
    "cf_link_id": "1996567",
    "link_id": "SS-1001-1",
    "link_status": "ACTIVE",
    "link_currency": "INR",
    "link_amount": 498,
    "link_amount_paid": 0,
    "link_url": "https://payments-test.cashfree.com/links/o1tf1nvcvjhg",
    "link_expiry_time": "2026-09-14T15:04:05+05:30",
    "link_qrcode": "data:image/png;base64,iVBORw0KGgo",
    "customer_details": {"customer_name": "Asha Verma", "customer_phone": "9876543210"},
    "link_meta": {"return_url": "https://api.testserver/pay/return/abc/", "upi_intent": False},
}
PAID_LINK = {**ACTIVE_LINK, "link_status": "PAID", "link_amount_paid": 498}
# https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/get-orders-for-a-payment-link
LINK_ORDERS = [
    {
        "cf_order_id": "2149460581",
        "order_id": "CFPay_U1mgll3c0e9g_ehdcjjbtckf",
        "order_status": "PAID",
        "order_amount": 498,
        "order_currency": "INR",
        "created_at": "2026-09-14T14:02:46+05:30",
    }
]
# https://www.cashfree.com/docs/api-reference/payments/latest/payments/get-payments-for-order
ORDER_PAYMENTS = [
    {
        "cf_payment_id": "12376124",
        "order_id": "CFPay_U1mgll3c0e9g_ehdcjjbtckf",
        "payment_status": "FAILED",
        "payment_amount": 498,
        "payment_currency": "INR",
    },
    {
        "cf_payment_id": "12376123",
        "order_id": "CFPay_U1mgll3c0e9g_ehdcjjbtckf",
        "payment_status": "SUCCESS",
        "payment_amount": 498,
        "payment_currency": "INR",
        "payment_time": "2026-09-14T14:15:06+05:30",
        "payment_completion_time": "2026-09-14T14:18:59+05:30",
        "is_captured": True,
    },
]


def provider(handler, *, mode="test", **kwargs) -> CashfreeProvider:
    options = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "mode": mode}
    options.update(kwargs)
    return CashfreeProvider(**options, transport=httpx.MockTransport(handler))


def link_request(**overrides) -> LinkRequest:
    values = {
        "reference_id": "SS-1001-1",
        "amount_paise": 24950,
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


def error(status: int, message: str, type_: str = "invalid_request_error") -> httpx.Response:
    return httpx.Response(status, json={"message": message, "code": "x", "type": type_})


@pytest.mark.parametrize(
    ("mode", "base"),
    [("test", "https://sandbox.cashfree.com/pg"), ("live", "https://api.cashfree.com/pg")],
)
def test_create_link_builds_the_documented_request(mode, base):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=ACTIVE_LINK)

    request = link_request()
    state = provider(handler, mode=mode).create_link(request)

    sent = seen[0]
    assert str(sent.url) == f"{base}/links"
    assert sent.headers["x-client-id"] == CLIENT_ID
    assert sent.headers["x-client-secret"] == CLIENT_SECRET
    assert sent.headers["x-api-version"] == API_VERSION
    body = json.loads(sent.content)
    assert Decimal(str(body.pop("link_amount"))) == Decimal("249.50")
    expiry = body.pop("link_expiry_time")
    assert expiry.endswith("+05:30")
    assert body == {
        "link_id": "SS-1001-1",
        "link_currency": "INR",
        "link_purpose": "Order SS-1001",
        "customer_details": {"customer_phone": "9876543210", "customer_name": "Asha Verma"},
        "link_partial_payments": False,
        "link_notify": {"send_sms": False, "send_email": False},
        "link_auto_reminders": False,
        "link_meta": {"return_url": "https://api.testserver/pay/return/abc/"},
        "link_notes": {"workspace_id": "w1", "order_id": "o1"},
    }
    assert state.provider_link_id == "SS-1001-1"
    assert state.short_url == ACTIVE_LINK["link_url"]
    assert state.status == CREATED
    assert state.amount_paise == 49800
    assert "link_qrcode" not in state.raw


def test_create_link_is_idempotent_on_link_id():
    def handler(request):
        if request.method == "POST":
            return error(409, "link_id already exists")
        assert request.url.path == "/pg/links/SS-1001-1"
        return httpx.Response(200, json=ACTIVE_LINK)

    assert provider(handler).create_link(link_request()).provider_link_id == "SS-1001-1"


def test_fetch_paid_link_reads_the_payment_id():
    def handler(request):
        path = request.url.path
        if path == "/pg/links/SS-1001-1":
            return httpx.Response(200, json=PAID_LINK)
        if path == "/pg/links/SS-1001-1/orders":
            assert request.url.params["status"] == "PAID"
            return httpx.Response(200, json=LINK_ORDERS)
        assert path == "/pg/orders/CFPay_U1mgll3c0e9g_ehdcjjbtckf/payments"
        return httpx.Response(200, json=ORDER_PAYMENTS)

    state = provider(handler).fetch_link("SS-1001-1")

    assert state.status == PAID
    assert state.amount_paid_paise == 49800
    assert state.currency == "INR"
    assert state.provider_payment_id == "12376123"
    assert state.paid_at.isoformat() == "2026-09-14T14:18:59+05:30"


def test_fetch_paid_link_survives_a_failing_payment_lookup():
    def handler(request):
        if request.url.path == "/pg/links/SS-1001-1":
            return httpx.Response(200, json=PAID_LINK)
        return error(500, "boom", "api_error")

    state = provider(handler).fetch_link("SS-1001-1")

    assert state.status == PAID
    assert state.provider_payment_id == ""


@pytest.mark.parametrize(
    ("link_status", "expected"),
    [
        ("ACTIVE", CREATED),
        ("PAID", PAID),
        ("COMPLETED", PAID),
        ("PARTIALLY_PAID", PARTIALLY_PAID),
        ("EXPIRED", EXPIRED),
        ("CANCELLED", CANCELLED),
    ],
)
def test_link_statuses(link_status, expected):
    data = {**ACTIVE_LINK, "link_status": link_status}

    def handler(request):
        if request.url.path == "/pg/links/SS-1001-1":
            return httpx.Response(200, json=data)
        return httpx.Response(200, json=[])

    assert provider(handler).fetch_link("SS-1001-1").status == expected


def test_cancel_link():
    def ok(request):
        return httpx.Response(200, json={**ACTIVE_LINK, "link_status": "CANCELLED"})

    assert provider(ok).cancel_link("SS-1001-1").status == CANCELLED

    def not_active(request):
        if request.method == "POST":
            return error(400, "link is not active")
        if request.url.path == "/pg/links/SS-1001-1":
            return httpx.Response(200, json=PAID_LINK)
        return httpx.Response(200, json=[])

    assert provider(not_active).cancel_link("SS-1001-1").status == PAID


@pytest.mark.parametrize(
    ("status_code", "retryable"), [(500, True), (502, True), (429, True), (400, False)]
)
def test_errors_are_mapped(status_code, retryable):
    with pytest.raises(PaymentProviderError) as caught:
        provider(lambda r: error(status_code, "nope")).fetch_link("SS-1001-1")

    assert caught.value.provider == "cashfree"
    assert caught.value.status_code == status_code
    assert caught.value.retryable is retryable
    assert CLIENT_SECRET not in str(caught.value)


def test_network_errors_are_retryable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(PaymentProviderError) as caught:
        provider(handler).fetch_link("SS-1001-1")

    assert caught.value.retryable is True


def test_verify_credentials():
    seen = []

    def not_found(request):
        seen.append(request)
        return error(404, "something is not found")

    provider(not_found).verify_credentials()
    assert seen[0].method == "GET"
    assert seen[0].url.path.startswith("/pg/links/")

    with pytest.raises(PaymentAccountInvalid):
        provider(
            lambda r: error(401, "authentication Failed", "authentication_error")
        ).verify_credentials()
    with pytest.raises(PaymentProviderError):
        provider(lambda r: error(500, "down", "api_error")).verify_credentials()
    with pytest.raises(PaymentAccountMissing):
        provider(not_found, mode="").verify_credentials()


def sign(timestamp: str, body: bytes, secret: str = CLIENT_SECRET) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


# https://www.cashfree.com/docs/api-reference/payments/latest/payment-links/webhooks
WEBHOOK_BODY = json.dumps(
    {
        "data": {
            "cf_link_id": 1576977,
            "link_id": "SS-1001-1",
            "link_status": "PAID",
            "link_currency": "INR",
            "link_amount": "498.00",
            "link_amount_paid": "498.00",
            "link_partial_payments": False,
            "link_purpose": "Order SS-1001",
            "link_created_at": "2026-09-14T07:13:41",
            "customer_details": {"customer_phone": "9876543210", "customer_name": "Asha"},
            "link_expiry_time": "2026-09-14T21:46:20",
            "link_notes": {"order_id": "o1"},
            "order": {
                "order_amount": "498.00",
                "order_id": "CFPay_U1mgll3c0e9g_ehdcjjbtckf",
                "order_expiry_time": "2026-09-14T07:34:50",
                "transaction_id": 1021206,
                "transaction_status": "SUCCESS",
            },
        },
        "type": "PAYMENT_LINK_EVENT",
        "version": 1,
        "event_time": "2026-09-14T12:55:06+05:30",
    }
).encode()


def test_webhook_signature_and_parsing():
    headers = {
        "x-webhook-timestamp": "1757834706",
        "x-webhook-signature": sign("1757834706", WEBHOOK_BODY),
    }

    [update] = provider(lambda r: None).parse_webhook(headers, WEBHOOK_BODY)

    assert update.event_type == "PAYMENT_LINK_EVENT"
    assert update.event_id == f"sha256:{hashlib.sha256(WEBHOOK_BODY).hexdigest()}"
    assert update.provider_link_id == "SS-1001-1"
    assert update.state.status == PAID
    assert update.state.amount_paid_paise == 49800
    assert update.state.amount_paise == 49800
    assert update.state.provider_payment_id == "1021206"

    [with_key] = provider(lambda r: None).parse_webhook(
        {**headers, "x-idempotency-key": "evt-1"}, WEBHOOK_BODY
    )
    assert with_key.event_id == "evt-1"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"x-webhook-timestamp": "1757834706"},
        {"x-webhook-timestamp": "1757834706", "x-webhook-signature": "bad"},
        {"x-webhook-timestamp": "1757834707", "x-webhook-signature": sign("1757834706", b"")},
        {
            "x-webhook-timestamp": "1757834706",
            "x-webhook-signature": sign("1757834706", WEBHOOK_BODY, "other-secret"),
        },
    ],
)
def test_webhook_rejects_bad_signatures(headers):
    with pytest.raises(InvalidWebhookSignature):
        provider(lambda r: None).parse_webhook(headers, WEBHOOK_BODY)


def test_money_and_phone_helpers():
    assert rupees_to_paise("249.50") == 24950
    assert rupees_to_paise(249.5) == 24950
    assert rupees_to_paise(498) == 49800
    assert rupees_to_paise("0.005") == 1
    assert rupees_to_paise("abc") is None
    assert rupees_to_paise(None) is None
    assert paise_to_rupees(24950) == Decimal("249.50")
    assert cashfree_phone("+919876543210") == "9876543210"
    assert cashfree_phone("+14155550100") == "14155550100"
