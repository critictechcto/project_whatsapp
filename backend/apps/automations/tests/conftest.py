import pytest

from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.factories import PhoneNumberFactory


@pytest.fixture
def number(workspace):
    """The workspace's default, registered number on a connected WABA."""
    return PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)


@pytest.fixture
def contact(workspace):
    return ContactFactory(
        workspace=workspace,
        name="Priya Sharma",
        email="priya@example.com",
        attributes={"city": "Pune", "order_id": 1042},
        marketing_opt_in_status=Contact.OptInStatus.OPTED_IN,
    )


@pytest.fixture
def conversation(contact, number):
    """Conversation with an open service window."""
    return ConversationFactory(
        workspace=contact.workspace, contact=contact, phone_number=number, window_open=True
    )


@pytest.fixture
def template(number):
    """Approved UTILITY template: ``Hi {{1}}, your order {{2}} has shipped.``"""
    return MessageTemplateFactory(waba=number.waba, status=MessageTemplate.Status.APPROVED)


@pytest.fixture
def inbound(conversation):
    """``inbound("PRICE")`` stores a received customer message in ``conversation``."""

    def make(text: str = "Hi", **kwargs):
        return MessageFactory(conversation=conversation, inbound=True, text=text, **kwargs)

    return make


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """``with commit():`` runs on_commit callbacks (events, task dispatch) when the block exits."""
    return lambda: django_capture_on_commit_callbacks(execute=True)
