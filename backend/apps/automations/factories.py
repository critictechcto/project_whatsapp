import factory

from apps.inbox.factories import MessageFactory
from apps.tenants.factories import WorkspaceFactory

from .models import AutomationRule, AutomationRun, BusinessHours


class AutomationRuleFactory(factory.django.DjangoModelFactory):
    """An active ``PRICE`` keyword rule that replies with text."""

    class Meta:
        model = AutomationRule

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Sequence(lambda n: f"Rule {n}")
    trigger = AutomationRule.Trigger.KEYWORD
    keywords = factory.LazyFunction(lambda: ["price"])
    keyword_match = AutomationRule.KeywordMatch.EXACT
    actions = factory.LazyFunction(
        lambda: [{"type": "send_text", "config": {"text": "Our prices start at ₹499."}}]
    )


class BusinessHoursFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BusinessHours
        django_get_or_create = ("workspace",)

    workspace = factory.SubFactory(WorkspaceFactory)
    enabled = True
    schedule = factory.LazyFunction(
        lambda: [{"day": day, "start": "10:00", "end": "19:00"} for day in range(6)]
    )


class AutomationRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AutomationRun

    message = factory.SubFactory(MessageFactory, inbound=True)
    conversation = factory.SelfAttribute("message.conversation")
    workspace = factory.SelfAttribute("message.workspace")
    rule = factory.SubFactory(AutomationRuleFactory, workspace=factory.SelfAttribute("..workspace"))
    status = AutomationRun.Status.SUCCEEDED
    detail = "Ran 1 action(s)."
