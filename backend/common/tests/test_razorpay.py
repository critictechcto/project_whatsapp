"""Shared Razorpay transport (httpx.MockTransport, no network) and webhook signatures."""

import hashlib
import hmac

import httpx
import pytest

from common import razorpay


def make_transport(handler) -> razorpay.RazorpayTransport:
    return razorpay.RazorpayTransport(
        key_id="rzp_test_merchant",
        key_secret="merchant-secret",
        transport=httpx.MockTransport(handler),
    )


def test_missing_keys_are_not_configured():
    with pytest.raises(razorpay.RazorpayNotConfigured):
        razorpay.RazorpayTransport(key_id="", key_secret="x")


def test_request_sends_basic_auth_json_and_params():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "plink_1"})

    body = make_transport(handler).request(
        "POST", "/payment_links", json={"amount": 100}, params={"count": 1}
    )

    assert body == {"id": "plink_1"}
    [request] = seen
    assert request.url.path == "/v1/payment_links"
    assert request.url.params["count"] == "1"
    assert request.headers["Authorization"].startswith("Basic ")
    assert request.content == b'{"amount":100}'


@pytest.mark.parametrize(
    ("status", "retryable", "auth"),
    [(400, False, False), (401, False, True), (429, True, False), (503, True, False)],
)
def test_error_mapping(status, retryable, auth):
    transport = make_transport(
        lambda request: httpx.Response(
            status, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Nope"}}
        )
    )

    with pytest.raises(razorpay.RazorpayError) as excinfo:
        transport.request("GET", "/payment_links")

    assert excinfo.value.status_code == status
    assert excinfo.value.code == "BAD_REQUEST_ERROR"
    assert str(excinfo.value) == "Nope"
    assert excinfo.value.retryable is retryable
    assert excinfo.value.is_auth_error is auth


def test_network_errors_are_retryable():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(razorpay.RazorpayError) as excinfo:
        make_transport(handler).request("GET", "/payment_links")

    assert excinfo.value.status_code is None
    assert excinfo.value.retryable


def test_non_object_response_is_an_error():
    transport = make_transport(lambda request: httpx.Response(200, json=[1]))

    with pytest.raises(razorpay.RazorpayError):
        transport.request("GET", "/payment_links")


def test_checked_id():
    assert razorpay.checked_id("plink_ABC123") == "plink_ABC123"
    for bad in ("", "../x", "a/b", 5):
        with pytest.raises(razorpay.RazorpayError):
            razorpay.checked_id(bad)


def test_webhook_signature():
    body = b'{"event":"payment_link.paid"}'
    signature = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()

    assert razorpay.webhook_signature_is_valid(body, signature, "whsec")
    assert razorpay.webhook_signature_is_valid(body, signature.upper(), "whsec")
    assert not razorpay.webhook_signature_is_valid(body, signature, "other")
    assert not razorpay.webhook_signature_is_valid(body, None, "whsec")
    assert not razorpay.webhook_signature_is_valid(body, signature, "")
