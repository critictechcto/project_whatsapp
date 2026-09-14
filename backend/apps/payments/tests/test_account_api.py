"""Payment account API: PATCH rules, verify, delete, webhook rotation, roles and secrets."""

import logging

import pytest

from apps.payments.exceptions import PaymentProviderError
from apps.payments.factories import PaymentAccountFactory
from apps.payments.models import PaymentAccount
from common.roles import Role

pytestmark = pytest.mark.django_db

ACCOUNT = "/api/v1/payments/account/"
VERIFY = f"{ACCOUNT}verify/"
ROTATE = f"{ACCOUNT}rotate-webhook/"
SECRET = "sk-very-secret-value"


def patch(client, data):
    return client.patch(ACCOUNT, data, format="json")


def test_razorpay_keys_set_mode_and_reset_status(auth_client, workspace):
    client = auth_client(Role.ADMIN)

    response = patch(client, {"key_id": "rzp_live_Abc123", "key_secret": SECRET})

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["provider"] == "razorpay"
    assert data["mode"] == "live"
    assert data["key_id"] == "rzp_live_Abc123"
    assert data["has_key_secret"] is True
    assert data["status"] == "unverified"
    assert data["webhook_url"].startswith("https://api.testserver/webhooks/payments/merchants/")
    assert SECRET.encode() not in response.content
    assert PaymentAccount.objects.get(workspace=workspace).key_secret == SECRET


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"key_id": "key_live_Abc123"}, "key_id"),
        ({"key_id": "rzp_live_"}, "key_id"),
        ({"key_id": "rzp_test_Abc123", "mode": "live"}, "mode"),
        ({"webhook_secret": ""}, "webhook_secret"),
        ({"provider": "paytm"}, "provider"),
    ],
)
def test_razorpay_validation(auth_client, payload, field):
    response = patch(auth_client(Role.ADMIN), payload)

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]


def test_razorpay_mode_must_match_a_saved_key(auth_client, workspace):
    PaymentAccountFactory(workspace=workspace, key_id="rzp_test_Abc123", mode="test")

    response = patch(auth_client(Role.ADMIN), {"mode": "live"})

    assert response.status_code == 400
    assert "mode" in response.json()["error"]["details"]


def test_changing_provider_clears_keys_and_secrets(auth_client, workspace):
    PaymentAccountFactory(workspace=workspace)

    response = patch(auth_client(Role.ADMIN), {"provider": "cashfree"})

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["provider"] == "cashfree"
    assert data["key_id"] == ""
    assert data["mode"] is None
    assert data["has_key_secret"] is False
    assert data["has_webhook_secret"] is False
    assert data["status"] == "not_configured"
    assert data["verified_at"] is None
    assert data["webhook_events"] == ["PAYMENT_LINK_EVENT"]


def test_cashfree_requires_mode_and_has_no_webhook_secret(auth_client, workspace):
    client = auth_client(Role.ADMIN)
    base = {"provider": "cashfree", "key_id": "TEST10123", "key_secret": SECRET}

    missing = patch(client, base)
    assert missing.status_code == 400
    assert "mode" in missing.json()["error"]["details"]

    webhook = patch(client, {**base, "mode": "test", "webhook_secret": "x"})
    assert webhook.status_code == 400
    assert "webhook_secret" in webhook.json()["error"]["details"]

    ok = patch(client, {**base, "mode": "test"})
    assert ok.status_code == 200, ok.content
    assert ok.json()["mode"] == "test"
    assert ok.json()["status"] == "unverified"
    assert not PaymentAccount.objects.filter(workspace=workspace, key_id="").exists()


def test_key_changes_reset_verification_but_webhook_secret_does_not(auth_client, workspace):
    PaymentAccountFactory(workspace=workspace, key_id="rzp_test_Abc123")
    client = auth_client(Role.ADMIN)

    webhook = patch(client, {"webhook_secret": "new-webhook-secret"})
    assert webhook.json()["status"] == "verified"

    same_key = patch(client, {"key_id": "rzp_test_Abc123"})
    assert same_key.json()["status"] == "verified"

    new_secret = patch(client, {"key_secret": "another-secret"})
    assert new_secret.json()["status"] == "unverified"
    assert new_secret.json()["verified_at"] is None


def test_verify_success(auth_client, workspace, fake_payments):
    PaymentAccountFactory(workspace=workspace, status="unverified", last_error="old")

    response = auth_client(Role.ADMIN).post(VERIFY)

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "verified"
    assert response.json()["verified_at"] is not None
    assert response.json()["last_error"] == ""
    assert fake_payments.calls_to("verify_credentials") == [""]


def test_verify_invalid_keys(auth_client, workspace, fake_payments, caplog):
    PaymentAccountFactory(workspace=workspace, key_secret=SECRET, status="unverified")
    fake_payments.credentials_valid = False
    caplog.set_level(logging.DEBUG)

    response = auth_client(Role.ADMIN).post(VERIFY)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "payment_account_invalid"
    account = PaymentAccount.objects.get(workspace=workspace)
    assert account.status == "invalid"
    assert account.last_error
    assert SECRET not in account.last_error
    assert SECRET not in caplog.text
    assert SECRET.encode() not in response.content


def test_verify_gateway_down_keeps_status(auth_client, workspace, fake_payments):
    PaymentAccountFactory(workspace=workspace, key_secret=SECRET, status="unverified")
    fake_payments.fail_next(
        "verify_credentials",
        PaymentProviderError(
            f"boom {SECRET}", provider="razorpay", status_code=502, retryable=True
        ),
    )

    response = auth_client(Role.ADMIN).post(VERIFY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_unavailable"
    account = PaymentAccount.objects.get(workspace=workspace)
    assert account.status == "unverified"
    assert "Could not reach" in account.last_error
    assert SECRET not in account.last_error


def test_verify_without_keys_or_mode(auth_client, workspace, fake_payments):
    client = auth_client(Role.ADMIN)

    missing = client.post(VERIFY)
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "payment_account_missing"

    PaymentAccountFactory(workspace=workspace, key_secret="")
    assert client.post(VERIFY).json()["error"]["code"] == "payment_account_missing"

    PaymentAccount.objects.filter(workspace=workspace).update(
        provider="cashfree", key_id="TEST1", key_secret=SECRET, mode=""
    )
    no_mode = client.post(VERIFY)
    assert no_mode.status_code == 400
    assert "mode" in no_mode.json()["error"]["details"]
    assert fake_payments.calls == []


def test_delete_is_owner_only(auth_client, workspace):
    PaymentAccountFactory(workspace=workspace)

    assert auth_client(Role.ADMIN).delete(ACCOUNT).status_code == 403
    assert auth_client(Role.OWNER).delete(ACCOUNT).status_code == 204
    assert not PaymentAccount.objects.filter(workspace=workspace).exists()
    assert auth_client(Role.OWNER).delete(ACCOUNT).status_code == 204


def test_rotate_webhook(auth_client, workspace):
    client = auth_client(Role.ADMIN)
    assert client.post(ROTATE).json()["error"]["code"] == "payment_account_missing"

    account = PaymentAccountFactory(workspace=workspace)
    old_token = account.webhook_token

    response = client.post(ROTATE)

    assert response.status_code == 200, response.content
    account.refresh_from_db()
    assert account.webhook_token != old_token
    assert response.json()["webhook_url"].endswith(f"/{account.webhook_token}/")


@pytest.mark.parametrize(
    ("method", "url"),
    [("patch", ACCOUNT), ("post", VERIFY), ("post", ROTATE), ("get", ACCOUNT)],
)
def test_agents_are_denied(auth_client, method, url):
    response = getattr(auth_client(Role.AGENT), method)(url, {}, format="json")

    assert response.status_code == 403


def test_account_is_isolated_per_workspace(auth_client, workspace, other_workspace):
    theirs = PaymentAccountFactory(workspace=other_workspace, key_id="rzp_test_Theirs1")
    client = auth_client(Role.ADMIN)

    assert client.get(ACCOUNT).json()["status"] == "not_configured"
    patch(client, {"key_id": "rzp_test_Mine1", "key_secret": SECRET})
    client.delete(ACCOUNT)

    theirs.refresh_from_db()
    assert theirs.key_id == "rzp_test_Theirs1"
    assert theirs.status == "verified"
