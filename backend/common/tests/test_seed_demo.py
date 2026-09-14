from io import StringIO

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.tenants.models import Membership, Workspace
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.management.commands import seed_demo
from common.roles import Role
from common.tests.fakes import install_module


def run(**options) -> str:
    out = StringIO()
    call_command("seed_demo", stdout=out, **options)
    return out.getvalue()


@pytest.fixture
def debug(settings):
    settings.DEBUG = True


@pytest.mark.django_db
def test_refuses_without_debug(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        run()

    assert not Workspace.objects.filter(slug=seed_demo.DEMO_WORKSPACE_SLUG).exists()


@pytest.mark.django_db
def test_creates_connected_demo_workspace(debug):
    output = run()

    user = get_user_model().objects.get(email=seed_demo.DEMO_EMAIL)
    assert user.check_password(seed_demo.DEMO_PASSWORD)
    workspace = Workspace.objects.get(slug=seed_demo.DEMO_WORKSPACE_SLUG)
    assert Membership.objects.get(workspace=workspace, user=user).role == Role.OWNER
    waba = WhatsAppBusinessAccount.objects.get(workspace=workspace)
    assert waba.status == WhatsAppBusinessAccount.Status.ACTIVE
    assert waba.onboarding_status == WhatsAppBusinessAccount.OnboardingStatus.COMPLETED
    assert waba.access_token == seed_demo.DEMO_ACCESS_TOKEN
    number = PhoneNumber.objects.get(workspace=workspace)
    assert number.waba == waba
    assert number.is_default is True
    assert number.registration_status == PhoneNumber.RegistrationStatus.REGISTERED
    assert seed_demo.DEMO_ACCESS_TOKEN not in output
    assert seed_demo.DEMO_PASSWORD not in output


@pytest.mark.django_db
def test_is_idempotent(debug):
    run()
    user = get_user_model().objects.get(email=seed_demo.DEMO_EMAIL)
    user.set_password("changed-by-developer")
    user.save()

    run()

    assert get_user_model().objects.filter(email=seed_demo.DEMO_EMAIL).count() == 1
    assert Workspace.objects.filter(slug=seed_demo.DEMO_WORKSPACE_SLUG).count() == 1
    assert Membership.objects.filter(user=user).count() == 1
    assert WhatsAppBusinessAccount.objects.filter(waba_id=seed_demo.DEMO_WABA_ID).count() == 1
    assert PhoneNumber.objects.filter(phone_number_id=seed_demo.DEMO_PHONE_NUMBER_ID).count() == 1
    user.refresh_from_db()
    assert user.check_password("changed-by-developer")


def demo_row_counts(workspace) -> dict[str, int]:
    from apps.automations.models import AutomationRule
    from apps.billing.models import Subscription
    from apps.campaigns.models import Campaign
    from apps.contacts.models import Contact
    from apps.inbox.models import Conversation, Message
    from apps.message_templates.models import MessageTemplate

    return {
        "contacts": Contact.objects.filter(workspace=workspace).count(),
        "templates": MessageTemplate.objects.filter(waba__workspace=workspace).count(),
        "conversations": Conversation.objects.filter(workspace=workspace).count(),
        "messages": Message.objects.filter(workspace=workspace).count(),
        "campaigns": Campaign.objects.filter(workspace=workspace).count(),
        "automation_rules": AutomationRule.objects.filter(workspace=workspace).count(),
        "subscriptions": Subscription.objects.filter(workspace=workspace).count(),
    }


@pytest.mark.django_db
def test_real_app_seeders_run_twice_without_duplicates(debug):
    first = run()
    workspace = Workspace.objects.get(slug=seed_demo.DEMO_WORKSPACE_SLUG)
    counts = demo_row_counts(workspace)
    second = run()

    for app in ("apps.inbox", "apps.campaigns", "apps.automations", "apps.billing"):
        assert f"Seeded {app}" in first
        assert f"Seeded {app}" in second
    assert all(counts.values()), counts
    assert demo_row_counts(workspace) == counts


@pytest.mark.django_db
def test_reuses_existing_user_by_email(debug, user):
    run(email=user.email.upper())

    workspace = Workspace.objects.get(slug=seed_demo.DEMO_WORKSPACE_SLUG)
    assert Membership.objects.get(workspace=workspace).user == user


def test_collects_app_seeders_in_installed_apps_order(monkeypatch):
    def seed_b(workspace):
        return None

    def seed_a(workspace):
        return None

    install_module(monkeypatch, "apps.bravo", package=True)
    install_module(monkeypatch, "apps.bravo.demo", seed=seed_b)
    install_module(monkeypatch, "apps.alpha", package=True)
    install_module(monkeypatch, "apps.alpha.demo", seed=seed_a)
    install_module(monkeypatch, "apps.nodemo", package=True)
    install_module(monkeypatch, "apps.noseed", package=True)
    install_module(monkeypatch, "apps.noseed.demo")
    install_module(monkeypatch, "thirdparty", package=True)
    install_module(monkeypatch, "thirdparty.demo", seed=seed_a)

    seeders = seed_demo.collect_demo_seeders(
        ["thirdparty", "apps.bravo", "apps.nodemo", "apps.noseed", "apps.alpha"]
    )

    assert seeders == [("apps.bravo", seed_b), ("apps.alpha", seed_a)]


def test_non_callable_seed_is_an_error(monkeypatch):
    install_module(monkeypatch, "apps.broken", package=True)
    install_module(monkeypatch, "apps.broken.demo", seed="nope")

    with pytest.raises(CommandError, match="callable"):
        seed_demo.collect_demo_seeders(["apps.broken"])


@pytest.mark.django_db
def test_runs_app_seeders_with_the_demo_workspace(debug, monkeypatch):
    calls = []
    install_module(monkeypatch, "apps.demoapp", package=True)
    install_module(monkeypatch, "apps.demoapp.demo", seed=lambda workspace: calls.append(workspace))
    monkeypatch.setattr(
        django_settings, "INSTALLED_APPS", [*django_settings.INSTALLED_APPS, "apps.demoapp"]
    )

    output = run()
    run()

    workspace = Workspace.objects.get(slug=seed_demo.DEMO_WORKSPACE_SLUG)
    assert calls == [workspace, workspace]
    assert "Seeded apps.demoapp" in output


@pytest.mark.django_db
def test_failing_seeder_rolls_everything_back(debug, monkeypatch):
    def seed(workspace):
        raise RuntimeError("seed failed")

    install_module(monkeypatch, "apps.failing", package=True)
    install_module(monkeypatch, "apps.failing.demo", seed=seed)
    monkeypatch.setattr(
        django_settings, "INSTALLED_APPS", [*django_settings.INSTALLED_APPS, "apps.failing"]
    )

    with pytest.raises(RuntimeError):
        run()

    assert not Workspace.objects.filter(slug=seed_demo.DEMO_WORKSPACE_SLUG).exists()
