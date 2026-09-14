import factory
from django.contrib.auth import get_user_model

DEFAULT_PASSWORD = "Str0ng-test-pass!"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name", locale="en_IN")
    password = factory.django.Password(DEFAULT_PASSWORD)
