import pytest

from apps.catalog.factories import ProductFactory
from apps.inbox.factories import ConversationFactory
from apps.orders.factories import StoreSettingsFactory
from apps.orders.models import Order
from apps.payments import services as payment_services
from apps.payments.factories import PaymentAccountFactory, PaymentLinkFactory
from apps.whatsapp.factories import PhoneNumberFactory


@pytest.fixture(autouse=True)
def graph(fake_graph):
    """Messages dispatched by executed on-commit callbacks go to the fake Graph client."""
    return fake_graph


@pytest.fixture
def number(workspace):
    """The workspace default number (the store number), connected and registered."""
    return PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)


@pytest.fixture
def store(workspace, number):
    return StoreSettingsFactory(workspace=workspace, store_name="Sharma Sweets")


@pytest.fixture
def conversation(workspace, store, number):
    """An Indian buyer on the store number with an open service window."""
    return ConversationFactory(workspace=workspace, phone_number=number, window_open=True)


@pytest.fixture
def product(workspace):
    return ProductFactory(workspace=workspace, name="Kaju Katli 250 g", price_paise=24900)


@pytest.fixture
def online(workspace):
    """A verified gateway account: online payments are ready."""
    return PaymentAccountFactory(workspace=workspace)


@pytest.fixture
def payment_links(monkeypatch):
    """Stub ``create_payment_link``: records the call and returns a created link."""
    calls = []

    def create_payment_link(**kwargs):
        calls.append(kwargs)
        return PaymentLinkFactory(
            order=Order.objects.get(pk=kwargs["order_id"]),
            reference_id=kwargs["reference_id"],
            amount_paise=kwargs["amount_paise"],
            expires_at=kwargs["expire_by"],
        )

    monkeypatch.setattr(payment_services, "create_payment_link", create_payment_link)
    return calls


@pytest.fixture
def cancelled_links(monkeypatch):
    """Stub ``cancel_payment_link``: marks the link cancelled and records its id."""
    cancelled = []

    def cancel_payment_link(payment_link):
        payment_link.status = "cancelled"
        payment_link.save()
        cancelled.append(payment_link.pk)
        return payment_link

    monkeypatch.setattr(payment_services, "cancel_payment_link", cancel_payment_link)
    return cancelled
