import factory

from apps.whatsapp.factories import WhatsAppBusinessAccountFactory

from .models import MessageTemplate


def standard_components(body: str = "Hi {{1}}, your order {{2}} has shipped.") -> list[dict]:
    """A valid UTILITY template body with one example per variable."""
    from .validators import variable_count

    component: dict = {"type": "BODY", "text": body}
    count = variable_count(body)
    if count:
        component["example"] = {"body_text": [[f"sample{n}" for n in range(1, count + 1)]]}
    return [component]


class MessageTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MessageTemplate

    waba = factory.SubFactory(WhatsAppBusinessAccountFactory)
    workspace = factory.SelfAttribute("waba.workspace")
    name = factory.Sequence(lambda n: f"order_update_{n}")
    language = "en"
    category = MessageTemplate.Category.UTILITY
    status = MessageTemplate.Status.DRAFT
    components = factory.LazyFunction(standard_components)
