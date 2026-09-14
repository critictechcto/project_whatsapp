"""Razorpay HTTP client (httpx.MockTransport, no network), fake client and signatures."""

import base64
import hashlib
import hmac
import json

import httpx
import pytest

from apps.billing import razorpay

KEY_ID = "rzp_test_key"
KEY_SECRET = "client-test-secret"


def make_client(handler) -> razorpay.HttpRazorpayClient:
    return razorpay.HttpRazorpayClient(
        key_id=KEY_ID, key_secret=KEY_SECRET, transport=httpx.MockTransport(handler)
    )


def test_timeout_comes_from_settings(settings):
    settings.RAZORPAY_TIMEOUT = 7.5

    from_settings = make_client(lambda request: httpx.Response(200, json={}))
    explicit = razorpay.HttpRazorpayClient(key_id=KEY_ID, key_secret=KEY_SECRET, timeout=3)

    assert from_settings._client.timeout == httpx.Timeout(7.5)
    assert explicit._client.timeout == httpx.Timeout(3)


def recording_handler(seen: list, response: httpx.Response):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    return handler


def test_create_subscription_posts_json_with_basic_auth():
    seen: list[httpx.Request] = []
    client = make_client(
        recording_handler(seen, httpx.Response(200, json={"id": "sub_123", "status": "created"}))
    )

    entity = client.create_subscription(
        plan_id="plan_x", total_count=12, notes={"workspace_id": "w1"}
    )

    [request] = seen
    assert entity == {"id": "sub_123", "status": "created"}
    assert request.method == "POST"
    assert str(request.url) == "https://api.razorpay.com/v1/subscriptions"
    credentials = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
    assert request.headers["authorization"] == f"Basic {credentials}"
    assert json.loads(request.content) == {
        "plan_id": "plan_x",
        "total_count": 12,
        "quantity": 1,
        "customer_notify": 1,
        "notes": {"workspace_id": "w1"},
    }


def test_fetch_subscription_gets_by_id():
    seen: list[httpx.Request] = []
    client = make_client(recording_handler(seen, httpx.Response(200, json={"id": "sub_123"})))

    assert client.fetch_subscription("sub_123") == {"id": "sub_123"}
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/v1/subscriptions/sub_123"


@pytest.mark.parametrize(("at_cycle_end", "flag"), [(True, 1), (False, 0)])
def test_cancel_subscription(at_cycle_end, flag):
    seen: list[httpx.Request] = []
    client = make_client(recording_handler(seen, httpx.Response(200, json={"id": "sub_123"})))

    client.cancel_subscription("sub_123", at_cycle_end=at_cycle_end)

    assert seen[0].url.path == "/v1/subscriptions/sub_123/cancel"
    assert json.loads(seen[0].content) == {"cancel_at_cycle_end": flag}


def test_api_errors_carry_razorpay_code_and_description():
    error = {
        "error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}
    }
    client = make_client(recording_handler([], httpx.Response(400, json=error)))

    with pytest.raises(razorpay.RazorpayError) as excinfo:
        client.fetch_subscription("sub_404")

    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "BAD_REQUEST_ERROR"
    assert str(excinfo.value) == "The id provided does not exist"
    assert excinfo.value.retryable is False


def test_server_errors_are_retryable():
    client = make_client(recording_handler([], httpx.Response(502, text="Bad gateway")))

    with pytest.raises(razorpay.RazorpayError) as excinfo:
        client.fetch_subscription("sub_1")

    assert excinfo.value.status_code == 502
    assert excinfo.value.retryable is True


def test_network_errors_become_razorpay_errors():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(razorpay.RazorpayError) as excinfo:
        make_client(handler).fetch_subscription("sub_1")

    assert excinfo.value.status_code is None
    assert excinfo.value.retryable is True
    assert KEY_SECRET not in str(excinfo.value)


def test_non_object_responses_are_errors():
    client = make_client(recording_handler([], httpx.Response(200, json=["unexpected"])))

    with pytest.raises(razorpay.RazorpayError):
        client.fetch_subscription("sub_1")


@pytest.mark.parametrize("subscription_id", ["../payments", "sub 1", ""])
def test_unsafe_subscription_ids_never_reach_razorpay(subscription_id):
    seen: list[httpx.Request] = []
    client = make_client(recording_handler(seen, httpx.Response(200, json={})))

    with pytest.raises(razorpay.RazorpayError):
        client.cancel_subscription(subscription_id, at_cycle_end=False)

    assert seen == []


def test_client_needs_keys():
    with pytest.raises(razorpay.RazorpayNotConfigured):
        razorpay.HttpRazorpayClient(key_id="", key_secret="secret")


def test_get_razorpay_client_returns_the_override(fake_razorpay):
    assert razorpay.get_razorpay_client() is fake_razorpay


def test_get_razorpay_client_builds_the_http_client_without_override():
    with razorpay.override_razorpay_client(None):
        client = razorpay.get_razorpay_client()

    assert isinstance(client, razorpay.HttpRazorpayClient)
    client.close()


def test_checkout_signature():
    secret = "key-secret"
    signature = hmac.new(secret.encode(), b"pay_1|sub_1", hashlib.sha256).hexdigest()

    def valid(**changes):
        arguments = {
            "payment_id": "pay_1",
            "subscription_id": "sub_1",
            "signature": signature,
            "secret": secret,
            **changes,
        }
        return razorpay.checkout_signature_is_valid(**arguments)

    assert valid()
    assert valid(signature=signature.upper())
    assert not valid(subscription_id="sub_2")
    assert not valid(payment_id="pay_2")
    assert not valid(signature="")
    assert not valid(signature="é" * 64)
    assert not valid(secret="")


def test_webhook_signature():
    body = b'{"event":"subscription.activated"}'
    signature = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()

    assert razorpay.webhook_signature_is_valid(body, signature, "hook-secret")
    assert not razorpay.webhook_signature_is_valid(body + b" ", signature, "hook-secret")
    assert not razorpay.webhook_signature_is_valid(body, None, "hook-secret")
    assert not razorpay.webhook_signature_is_valid(body, signature, "")


def test_plan_id_lookups(settings):
    assert razorpay.plan_id_for("pro", "annual") == "plan_test_pro_annual"
    assert razorpay.plan_for_razorpay_plan_id("plan_test_starter_monthly") == (
        "starter",
        "monthly",
    )
    assert razorpay.plan_for_razorpay_plan_id("plan_unknown") is None
    assert razorpay.plan_for_razorpay_plan_id(None) is None

    settings.RAZORPAY_PLAN_IDS = {}
    with pytest.raises(razorpay.RazorpayNotConfigured):
        razorpay.plan_id_for("pro", "monthly")


def test_fake_client_records_calls_and_fails_on_demand(fake_razorpay):
    entity = fake_razorpay.create_subscription(plan_id="plan_x", total_count=10, notes={})

    assert entity["status"] == "created"
    assert fake_razorpay.fetch_subscription(entity["id"])["plan_id"] == "plan_x"
    cancelled = fake_razorpay.cancel_subscription(entity["id"], at_cycle_end=False)
    assert cancelled["status"] == "cancelled"
    assert fake_razorpay.calls_to("cancel_subscription") == [
        {"subscription_id": entity["id"], "at_cycle_end": False}
    ]

    with pytest.raises(razorpay.RazorpayError):
        fake_razorpay.fetch_subscription("sub_missing")
    fake_razorpay.fail_with = razorpay.RazorpayError("down")
    with pytest.raises(razorpay.RazorpayError, match="down"):
        fake_razorpay.create_subscription(plan_id="plan_x", total_count=10, notes={})
