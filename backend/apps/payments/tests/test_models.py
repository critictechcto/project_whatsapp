"""Payments models and the implemented services."""

import pytest
from django.db import IntegrityError, transaction

from apps.orders.factories import OrderFactory
from apps.payments import services
from apps.payments.factories import PaymentAccountFactory, PaymentLinkFactory
from apps.payments.models import PaymentAccount, PaymentLink
from apps.payments.schema_enums import (
    PAYMENT_ACCOUNT_STATUSES,
    PAYMENT_LINK_STATUSES,
    PAYMENT_MODES,
    PAYMENT_PROVIDERS,
)

pytestmark = pytest.mark.django_db


def test_reference_id_is_unique_per_workspace(workspace, other_workspace):
    PaymentLinkFactory(order=OrderFactory(workspace=workspace), reference_id="SS-1001-1")
    PaymentLinkFactory(order=OrderFactory(workspace=other_workspace), reference_id="SS-1001-1")

    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentLinkFactory(order=OrderFactory(workspace=workspace), reference_id="SS-1001-1")


def test_webhook_tokens_are_unique_and_random(workspace, other_workspace):
    first = PaymentAccountFactory(workspace=workspace)
    second = PaymentAccountFactory(workspace=other_workspace)

    assert len(first.webhook_token) >= 40
    assert first.webhook_token != second.webhook_token


def test_secrets_are_encrypted_at_rest(workspace):
    account = PaymentAccountFactory(workspace=workspace, key_secret="very-secret-value")

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key_secret FROM payments_paymentaccount WHERE workspace_id = %s",
            [workspace.pk],
        )
        stored = cursor.fetchone()[0]
    assert "very-secret-value" not in stored
    account.refresh_from_db()
    assert account.key_secret == "very-secret-value"


def test_online_payments_ready(workspace):
    assert services.get_account(workspace) is None
    assert services.online_payments_ready(workspace) is False

    account = PaymentAccountFactory(workspace=workspace, status="unverified")
    assert services.get_account(workspace) == account
    assert services.online_payments_ready(workspace) is False

    account.status = "verified"
    account.save()
    assert services.online_payments_ready(workspace) is True

    account.webhook_secret = ""
    account.save()
    assert services.online_payments_ready(workspace) is True

    account.mode = ""
    account.save()
    assert services.online_payments_ready(workspace) is False


def test_webhook_url(workspace):
    account = PaymentAccountFactory(workspace=workspace)

    assert services.webhook_url(account) == (
        f"https://api.testserver/webhooks/payments/merchants/{account.webhook_token}/"
    )
    assert services.webhook_url(PaymentAccount(workspace=workspace)) == ""


def test_return_url():
    link = PaymentLinkFactory()

    assert services.return_url(link) == f"https://api.testserver/pay/return/{link.pk}/"


def test_model_choices_match_contract_enums():
    assert tuple(PaymentAccount.Status.values) == PAYMENT_ACCOUNT_STATUSES
    assert tuple(PaymentLink.Status.values) == PAYMENT_LINK_STATUSES
    assert tuple(PaymentAccount.Provider.values) == PAYMENT_PROVIDERS
    assert tuple(PaymentAccount.Mode.values) == PAYMENT_MODES
