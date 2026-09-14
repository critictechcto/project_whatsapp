import factory

from apps.orders.factories import OrderFactory
from apps.tenants.factories import WorkspaceFactory

from .models import PaymentAccount, PaymentLink, PaymentWebhookEvent


class PaymentAccountFactory(factory.django.DjangoModelFactory):
    """A verified test-mode Razorpay account with both secrets set."""

    class Meta:
        model = PaymentAccount

    workspace = factory.SubFactory(WorkspaceFactory)
    key_id = factory.Sequence(lambda n: f"rzp_test_{n:014d}")
    key_secret = factory.Sequence(lambda n: f"test-key-secret-{n}")
    webhook_secret = factory.Sequence(lambda n: f"test-webhook-secret-{n}")
    status = PaymentAccount.Status.VERIFIED


class PaymentLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentLink

    order = factory.SubFactory(OrderFactory)
    workspace = factory.SelfAttribute("order.workspace")
    provider_link_id = factory.Sequence(lambda n: f"plink_{n:014d}")
    reference_id = factory.Sequence(lambda n: f"LNK-{1001 + n}-1")
    short_url = factory.Sequence(lambda n: f"https://rzp.io/i/test{n}")
    amount_paise = factory.LazyAttribute(lambda o: o.order.total_paise)
    status = PaymentLink.Status.CREATED


class PaymentWebhookEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentWebhookEvent

    workspace = factory.SubFactory(WorkspaceFactory)
    event_id = factory.Sequence(lambda n: f"evt_{n:014d}")
    event_type = "payment_link.paid"
