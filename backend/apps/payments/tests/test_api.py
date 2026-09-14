"""Payments API and the merchant webhook stub: reads, secrets, roles and tenant isolation."""

import pytest

from apps.orders.factories import OrderFactory
from apps.payments.factories import PaymentAccountFactory, PaymentLinkFactory
from apps.payments.models import PaymentAccount
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

ACCOUNT = "/api/v1/payments/account/"
LINKS = "/api/v1/payments/links/"
WEBHOOK = "/webhooks/razorpay/merchants/"


def test_account_without_a_row_reads_as_not_configured(auth_client, workspace):
    response = auth_client(Role.ADMIN).get(ACCOUNT)

    assert response.status_code == 200, response.content
    assert response.json() == {
        "provider": "razorpay",
        "mode": None,
        "key_id": "",
        "has_key_secret": False,
        "has_webhook_secret": False,
        "status": "not_configured",
        "verified_at": None,
        "last_error": "",
        "webhook_url": "",
        "webhook_events": [
            "payment_link.paid",
            "payment_link.partially_paid",
            "payment_link.expired",
            "payment_link.cancelled",
        ],
        "updated_at": None,
    }
    assert not PaymentAccount.objects.filter(workspace=workspace).exists()


def test_account_never_returns_secrets(auth_client, workspace):
    account = PaymentAccountFactory(
        workspace=workspace,
        key_id="rzp_live_ABC123",
        key_secret="sk-do-not-leak",
        webhook_secret="wh-do-not-leak",
    )

    response = auth_client(Role.ADMIN).get(ACCOUNT)

    assert response.status_code == 200, response.content
    data = response.json()
    assert "key_secret" not in data
    assert "webhook_secret" not in data
    assert b"do-not-leak" not in response.content
    assert data["mode"] == "live"
    assert data["has_key_secret"] is True
    assert data["has_webhook_secret"] is True
    assert data["status"] == "verified"
    assert data["webhook_url"] == (
        f"https://api.testserver/webhooks/razorpay/merchants/{account.webhook_token}/"
    )


def test_account_is_admin_only(auth_client, workspace):
    assert auth_client(Role.AGENT).get(ACCOUNT).status_code == 403


@pytest.mark.parametrize(
    ("method", "path", "role", "below"),
    [
        ("patch", "", Role.ADMIN, Role.AGENT),
        ("delete", "", Role.OWNER, Role.ADMIN),
        ("post", "verify/", Role.ADMIN, Role.AGENT),
        ("post", "rotate-webhook/", Role.ADMIN, Role.AGENT),
    ],
)
def test_account_writes_are_role_gated_stubs(auth_client, workspace, method, path, role, below):
    url = f"{ACCOUNT}{path}"

    denied = getattr(auth_client(below), method)(url, {}, format="json")
    allowed = getattr(auth_client(role), method)(url, {}, format="json")

    assert denied.status_code == 403, denied.content
    assert allowed.status_code == 501, allowed.content
    assert allowed.json()["error"]["code"] == "not_implemented"


def test_links_list_filters_and_isolation(auth_client, workspace, other_workspace):
    order = OrderFactory(workspace=workspace)
    expired = PaymentLinkFactory(order=order, status="expired")
    paid = PaymentLinkFactory(order=order, status="paid")
    other = PaymentLinkFactory(order=OrderFactory(workspace=workspace))
    client = auth_client(Role.VIEWER)

    response = client.get(LINKS)
    assert response.status_code == 200, response.content
    assert result_ids(response) == {str(expired.pk), str(paid.pk), str(other.pk)}
    assert result_ids(client.get(LINKS, {"order": str(order.pk)})) == {
        str(expired.pk),
        str(paid.pk),
    }
    assert result_ids(client.get(LINKS, {"status": "paid"})) == {str(paid.pk)}
    assert client.get(LINKS, {"status": "lost"}).status_code == 400
    assert client.get(LINKS, {"order": "nope"}).status_code == 400

    assert_tenant_isolated(
        auth_client(workspace=other_workspace), object_id=paid.pk, list_url=LINKS
    )


def test_merchant_webhook_unknown_token_is_404(api_client):
    response = api_client.post(
        f"{WEBHOOK}unknown-token/", data=b"{}", content_type="application/json"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_merchant_webhook_known_token_is_not_implemented(api_client, workspace):
    account = PaymentAccountFactory(workspace=workspace)

    response = api_client.post(
        f"{WEBHOOK}{account.webhook_token}/", data=b"{}", content_type="application/json"
    )

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"
    assert api_client.get(f"{WEBHOOK}{account.webhook_token}/").status_code == 405
