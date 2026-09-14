import pytest

from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact
from apps.inbox.factories import ConversationFactory
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.factories import PhoneNumberFactory
from common import events

INBOX_SIGNALS = (events.message_recorded, events.message_delivery_updated)


class EventRecorder:
    def __init__(self) -> None:
        self.events: list = []

    def __call__(self, sender, event, **kwargs) -> None:
        self.events.append(event)

    def of(self, event_class: type) -> list:
        return [event for event in self.events if isinstance(event, event_class)]


@pytest.fixture
def recorded():
    """Every MessageRecorded / MessageDeliveryUpdated emitted during the test."""
    recorder = EventRecorder()
    for signal in INBOX_SIGNALS:
        signal.connect(recorder, weak=False)
    yield recorder
    for signal in INBOX_SIGNALS:
        signal.disconnect(recorder)


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """``with commit():`` runs on_commit callbacks (events, task dispatch) when the block exits."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


@pytest.fixture
def number(workspace):
    """The workspace's default, registered number on a connected WABA."""
    return PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)


@pytest.fixture
def contact(workspace):
    return ContactFactory(workspace=workspace, marketing_opt_in_status=Contact.OptInStatus.OPTED_IN)


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
