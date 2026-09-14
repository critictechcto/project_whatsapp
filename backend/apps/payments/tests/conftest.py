from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.orders.factories import OrderFactory
from apps.payments import services
from apps.payments.factories import PaymentAccountFactory
from apps.payments.testing import fake_payments  # noqa: F401  (fixture)
from common.events import payment_link_cancelled, payment_link_expired, payment_link_paid


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def payment_events():
    """Every PaymentLinkPaid/Expired/Cancelled event sent during the test."""
    received = []

    def receiver(sender, event, **kwargs):
        received.append(event)

    signals = (payment_link_paid, payment_link_expired, payment_link_cancelled)
    for signal in signals:
        signal.connect(receiver, weak=False)
    yield received
    for signal in signals:
        signal.disconnect(receiver)


@pytest.fixture
def account(workspace):
    return PaymentAccountFactory(workspace=workspace)


@pytest.fixture
def order(workspace):
    return OrderFactory(
        workspace=workspace,
        status="pending_payment",
        payment_status="unpaid",
        payment_method="online",
        total_paise=49800,
    )


@pytest.fixture
def make_link(workspace, order, account, fake_payments):  # noqa: F811
    def make(**overrides):
        kwargs = {
            "workspace": workspace,
            "order_id": order.pk,
            "reference_id": f"{order.number}-1",
            "amount_paise": order.total_paise,
            "description": f"Order {order.number}",
            "customer_name": "Asha Verma",
            "customer_phone_e164": "+919876543210",
            "expire_by": timezone.now() + timedelta(minutes=30),
        }
        kwargs.update(overrides)
        return services.create_payment_link(**kwargs)

    return make
