from datetime import timedelta

import factory
from django.utils import timezone

from apps.accounts.factories import UserFactory
from common.roles import Role

from .models import Invitation, Membership, Workspace


class WorkspaceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Workspace

    name = factory.Faker("company", locale="en_IN")
    slug = factory.Sequence(lambda n: f"workspace-{n}")


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    workspace = factory.SubFactory(WorkspaceFactory)
    user = factory.SubFactory(UserFactory)
    role = Role.AGENT


class InvitationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invitation

    workspace = factory.SubFactory(WorkspaceFactory)
    email = factory.Sequence(lambda n: f"invitee{n}@example.com")
    role = Role.AGENT
    token_hash = factory.Sequence(lambda n: Invitation.hash_token(f"token-{n}"))
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
