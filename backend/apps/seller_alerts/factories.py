from datetime import timedelta

import factory
from django.utils import timezone

from apps.orders.factories import OrderFactory
from apps.tenants.factories import WorkspaceFactory

from .models import AlertMessage, AlertRecipient, PendingSellerReply


class AlertRecipientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AlertRecipient

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Faker("first_name", locale="en_IN")
    phone_e164 = factory.Sequence(lambda n: f"+9197{n % 100_000_000:08d}")
    wa_id = factory.LazyAttribute(lambda o: o.phone_e164.removeprefix("+"))
    status = AlertRecipient.Status.VERIFIED
    verified_at = factory.LazyFunction(timezone.now)


class AlertMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AlertMessage

    recipient = factory.SubFactory(AlertRecipientFactory)
    workspace = factory.SelfAttribute("recipient.workspace")
    kind = AlertMessage.Kind.NEW_ORDER
    to_wa_id = factory.SelfAttribute("recipient.wa_id")
    wamid = factory.Sequence(lambda n: f"wamid.ALERT{n:010d}")
    status = AlertMessage.Status.SENT


class PendingSellerReplyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PendingSellerReply

    recipient = factory.SubFactory(AlertRecipientFactory)
    workspace = factory.SelfAttribute("recipient.workspace")
    order = factory.SubFactory(OrderFactory, workspace=factory.SelfAttribute("..workspace"))
    action = PendingSellerReply.Action.AWAITING_AWB
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=30))
