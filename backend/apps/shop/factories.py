from datetime import timedelta

import factory
from django.utils import timezone

from apps.inbox.factories import ConversationFactory

from .models import SESSION_TTL_HOURS, BotSession


class BotSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BotSession

    conversation = factory.SubFactory(ConversationFactory)
    workspace = factory.SelfAttribute("conversation.workspace")
    state = BotSession.State.IDLE
    cart = factory.LazyFunction(list)
    context = factory.LazyFunction(dict)
    last_message_at = factory.LazyFunction(timezone.now)
    expires_at = factory.LazyAttribute(
        lambda o: o.last_message_at + timedelta(hours=SESSION_TTL_HOURS)
    )
