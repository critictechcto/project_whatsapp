import re

import factory

from apps.tenants.factories import WorkspaceFactory

from .models import PhoneNumber, WhatsAppBusinessAccount


class WhatsAppBusinessAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WhatsAppBusinessAccount

    workspace = factory.SubFactory(WorkspaceFactory)
    waba_id = factory.Sequence(lambda n: f"10{n:013d}")
    name = factory.Faker("company", locale="en_IN")
    access_token = factory.Sequence(lambda n: f"EAAG-test-token-{n}")
    status = WhatsAppBusinessAccount.Status.ACTIVE
    onboarding_status = WhatsAppBusinessAccount.OnboardingStatus.COMPLETED


class PhoneNumberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PhoneNumber

    waba = factory.SubFactory(WhatsAppBusinessAccountFactory)
    workspace = factory.SelfAttribute("waba.workspace")
    phone_number_id = factory.Sequence(lambda n: f"20{n:013d}")
    display_phone_number = factory.Sequence(lambda n: f"+91 98000 {n % 100000:05d}")
    phone_e164 = factory.LazyAttribute(lambda o: "+" + re.sub(r"\D", "", o.display_phone_number))
    verified_name = "Test Business"
    quality_rating = PhoneNumber.QualityRating.GREEN
    messaging_limit_tier = "TIER_1K"
    registration_status = PhoneNumber.RegistrationStatus.REGISTERED
