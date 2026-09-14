import factory

from apps.contacts.factories import ContactFactory
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.factories import PhoneNumberFactory

from .models import Campaign, CampaignRecipient


def default_mapping() -> dict:
    """Mapping for the factory template body ``Hi {{1}}, your order {{2}} has shipped.``"""
    return {
        "body": [
            {"source": "contact_field", "value": "name", "fallback": "there"},
            {"source": "static", "value": "ORD-1001", "fallback": ""},
        ],
        "header": None,
        "buttons": {},
    }


class CampaignFactory(factory.django.DjangoModelFactory):
    """A draft on an approved template of the phone number's WABA."""

    class Meta:
        model = Campaign

    phone_number = factory.SubFactory(PhoneNumberFactory)
    workspace = factory.SelfAttribute("phone_number.workspace")
    template = factory.SubFactory(
        MessageTemplateFactory,
        waba=factory.SelfAttribute("..phone_number.waba"),
        status=MessageTemplate.Status.APPROVED,
    )
    template_snapshot = factory.LazyAttribute(
        lambda o: (
            {
                "id": str(o.template.pk),
                "name": o.template.name,
                "language": o.template.language,
                "category": o.template.category,
            }
            if o.template
            else {}
        )
    )
    name = factory.Sequence(lambda n: f"Campaign {n}")
    status = Campaign.Status.DRAFT
    audience = factory.LazyFunction(lambda: {"tag_ids": [], "match": "any", "contact_ids": []})
    variable_mapping = factory.LazyFunction(default_mapping)


class CampaignRecipientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CampaignRecipient

    campaign = factory.SubFactory(CampaignFactory)
    workspace = factory.SelfAttribute("campaign.workspace")
    contact = factory.SubFactory(ContactFactory, workspace=factory.SelfAttribute("..workspace"))
    status = CampaignRecipient.Status.PENDING
    params = factory.LazyFunction(lambda: {"body": ["Asha", "ORD-1001"], "header": None})
