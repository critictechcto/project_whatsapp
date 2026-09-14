import factory

from apps.tenants.factories import WorkspaceFactory

from .models import Contact, Tag


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Sequence(lambda n: f"tag-{n}")


class ContactFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Contact
        skip_postgeneration_save = True

    workspace = factory.SubFactory(WorkspaceFactory)
    phone_e164 = factory.Sequence(lambda n: f"+9198{n % 100_000_000:08d}")
    wa_id = factory.LazyAttribute(lambda o: o.phone_e164.removeprefix("+"))
    name = factory.Faker("name", locale="en_IN")

    @factory.post_generation
    def tags(self, create, extracted, **kwargs):
        if create and extracted:
            self.tags.add(*extracted)
