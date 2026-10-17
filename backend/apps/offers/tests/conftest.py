import pytest

from apps.billing import entitlements
from apps.catalog.factories import ProductFactory
from apps.contacts.factories import ContactFactory
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Message
from apps.offers.factories import OfferCodeFactory
from apps.orders.factories import StoreSettingsFactory
from apps.whatsapp.factories import PhoneNumberFactory
from common.events import MessageRecorded


@pytest.fixture(autouse=True)
def _no_network(fake_graph):
    return fake_graph


@pytest.fixture
def number(workspace):
    return PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)


@pytest.fixture
def contact(workspace):
    return ContactFactory(workspace=workspace, name="Asha Verma", phone_e164="+919812345701")


@pytest.fixture
def conversation(contact, number):
    return ConversationFactory(
        workspace=contact.workspace, contact=contact, phone_number=number, window_open=True
    )


@pytest.fixture
def store(workspace, number):
    return StoreSettingsFactory(workspace=workspace, enabled=True, store_name="Sharma Sweets")


@pytest.fixture
def product(workspace):
    return ProductFactory(workspace=workspace, name="Kaju Katli 500g", price_paise=59900)


@pytest.fixture
def offer(workspace):
    return OfferCodeFactory(
        workspace=workspace,
        code="DIWALI",
        reply_text="Happy Diwali! 10% off your next order.",
        discount_type="percent",
        discount_value=10,
    )


@pytest.fixture
def no_commerce(monkeypatch):
    real = entitlements.has_feature

    def has_feature(workspace, feature):
        return feature != entitlements.COMMERCE and real(workspace, feature)

    monkeypatch.setattr(entitlements, "has_feature", has_feature)


@pytest.fixture
def inbound(conversation):
    def make(text="DIWALI", **kwargs):
        return MessageFactory(conversation=conversation, inbound=True, text=text, **kwargs)

    return make


def recorded_event(message: Message) -> MessageRecorded:
    conversation = message.conversation
    return MessageRecorded(
        workspace_id=message.workspace_id,
        message_id=message.pk,
        conversation_id=conversation.pk,
        contact_id=conversation.contact_id,
        phone_number_id=conversation.phone_number_id,
        direction=message.direction,
        source=message.source,
        source_ref=message.source_ref,
        type=message.type,
        text=message.text,
        reply_id=None,
        wamid=message.wamid,
        is_first_inbound=False,
        contact_created=False,
        created_at=message.created_at,
    )
