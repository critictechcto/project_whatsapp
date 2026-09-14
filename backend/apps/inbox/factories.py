from datetime import timedelta

import factory
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.contacts.factories import ContactFactory
from apps.tenants.factories import WorkspaceFactory
from apps.whatsapp.factories import PhoneNumberFactory

from .models import Conversation, ConversationNote, MediaAsset, Message


class ConversationFactory(factory.django.DjangoModelFactory):
    """Contact and phone number are created in the conversation's workspace.

    Use ``ConversationFactory(window_open=True)`` for an open 24-hour service window.
    """

    class Meta:
        model = Conversation

    class Params:
        window_open = factory.Trait(
            last_inbound_at=factory.LazyFunction(lambda: timezone.now() - timedelta(hours=1)),
            last_message_at=factory.LazyFunction(lambda: timezone.now() - timedelta(hours=1)),
            service_window_expires_at=factory.LazyFunction(
                lambda: timezone.now() + timedelta(hours=23)
            ),
        )

    workspace = factory.SubFactory(WorkspaceFactory)
    contact = factory.SubFactory(ContactFactory, workspace=factory.SelfAttribute("..workspace"))
    phone_number = factory.SubFactory(
        PhoneNumberFactory, waba__workspace=factory.SelfAttribute("...workspace")
    )
    status = Conversation.Status.OPEN


class MediaAssetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MediaAsset

    workspace = factory.SubFactory(WorkspaceFactory)
    file = factory.django.FileField(filename="photo.jpg", data=b"\xff\xd8\xff fake jpeg")
    mime_type = "image/jpeg"
    file_name = "photo.jpg"
    size = factory.LazyAttribute(lambda o: o.file.size if o.file else 0)


class MessageFactory(factory.django.DjangoModelFactory):
    """A sent outbound text message; ``MessageFactory(inbound=True)`` for a received one."""

    class Meta:
        model = Message

    class Params:
        inbound = factory.Trait(
            direction=Message.Direction.INBOUND,
            status=Message.Status.RECEIVED,
            source=Message.Source.INBOUND,
            sent_at=factory.LazyFunction(timezone.now),
        )

    conversation = factory.SubFactory(ConversationFactory)
    workspace = factory.SelfAttribute("conversation.workspace")
    direction = Message.Direction.OUTBOUND
    type = Message.Type.TEXT
    text = factory.Faker("sentence")
    status = Message.Status.SENT
    source = Message.Source.INBOX
    wamid = factory.Sequence(lambda n: f"wamid.TEST{n:010d}")


class ConversationNoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ConversationNote

    conversation = factory.SubFactory(ConversationFactory)
    workspace = factory.SelfAttribute("conversation.workspace")
    author = factory.SubFactory(UserFactory)
    body = factory.Faker("sentence")
