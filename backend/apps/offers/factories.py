import factory

from apps.contacts.factories import ContactFactory
from apps.tenants.factories import WorkspaceFactory

from .models import OfferClaim, OfferCode


class OfferCodeFactory(factory.django.DjangoModelFactory):
    """An active 10% off code with no dates or limits."""

    class Meta:
        model = OfferCode

    workspace = factory.SubFactory(WorkspaceFactory)
    code = factory.Sequence(lambda n: f"OFFER{n}")
    title = "Festive offer"
    reply_text = "Thanks! You get 10% off your next order."
    discount_type = OfferCode.DiscountType.PERCENT
    discount_value = 10


class OfferClaimFactory(factory.django.DjangoModelFactory):
    """A ``claimed`` claim; the contact is created in the offer's workspace."""

    class Meta:
        model = OfferClaim

    offer = factory.SubFactory(OfferCodeFactory)
    workspace = factory.SelfAttribute("offer.workspace")
    contact = factory.SubFactory(ContactFactory, workspace=factory.SelfAttribute("..workspace"))
    status = OfferClaim.Status.CLAIMED
