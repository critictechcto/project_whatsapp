import pytest
from django.db import IntegrityError, transaction

from apps.inbox.factories import (
    ConversationFactory,
    ConversationNoteFactory,
    MediaAssetFactory,
    MessageFactory,
)
from apps.inbox.models import Conversation, Message

pytestmark = pytest.mark.django_db


# The values in docs/contracts/wave-2.md; frontend types and schema enums depend on them.
@pytest.mark.parametrize(
    ("choices", "values"),
    [
        (Conversation.Status, ["open", "pending", "closed"]),
        (Message.Direction, ["inbound", "outbound"]),
        (
            Message.Type,
            [
                "text",
                "image",
                "video",
                "audio",
                "document",
                "sticker",
                "location",
                "contacts",
                "interactive",
                "button",
                "reaction",
                "template",
                "order",
                "unsupported",
            ],
        ),
        (
            Message.Status,
            ["queued", "sending", "sent", "delivered", "read", "failed", "received"],
        ),
        (Message.Source, ["inbound", "inbox", "campaign", "automation", "api"]),
    ],
)
def test_enum_values_match_the_contract(choices, values):
    assert choices.values == values


def test_factories_keep_everything_in_one_workspace():
    note = ConversationNoteFactory()
    message = MessageFactory(conversation=note.conversation)
    conversation = note.conversation

    assert conversation.contact.workspace == conversation.workspace
    assert conversation.phone_number.workspace == conversation.workspace
    assert conversation.phone_number.waba.workspace == conversation.workspace
    assert message.workspace == note.workspace == conversation.workspace
    assert MediaAssetFactory().file.read()


def test_one_conversation_per_contact_and_number():
    conversation = ConversationFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        ConversationFactory(
            workspace=conversation.workspace,
            contact=conversation.contact,
            phone_number=conversation.phone_number,
        )


def test_idempotency_key_is_unique_per_workspace_when_set():
    conversation = ConversationFactory()
    MessageFactory(conversation=conversation, idempotency_key=None)
    MessageFactory(conversation=conversation, idempotency_key=None)
    MessageFactory(conversation=conversation, idempotency_key="inbox:1")
    MessageFactory(idempotency_key="inbox:1")  # another workspace

    with pytest.raises(IntegrityError), transaction.atomic():
        MessageFactory(conversation=conversation, idempotency_key="inbox:1")


def test_wamid_is_unique_but_optional():
    conversation = ConversationFactory()
    MessageFactory(conversation=conversation, wamid=None)
    MessageFactory(conversation=conversation, wamid=None)
    MessageFactory(conversation=conversation, wamid="wamid.A")

    with pytest.raises(IntegrityError), transaction.atomic():
        MessageFactory(conversation=conversation, wamid="wamid.A")
