"""``manage.py seed_demo``: a demo workspace for local development.

Creates (or reuses) a demo owner, a ``demo`` workspace and a connected WhatsApp Business Account
with a registered default phone number, then runs each local app's optional demo seeder:
``apps/<app>/demo.py`` defining ``seed(workspace)``, called in ``INSTALLED_APPS`` order inside one
transaction. Seeders must be idempotent (``get_or_create`` on natural keys), so the command can
run again safely.

The WhatsApp account carries a placeholder token; it never reaches Meta (use the fake Graph
client locally). Refuses to run unless ``DEBUG`` is on.
"""

import importlib
import importlib.util
from collections.abc import Callable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.tenants.models import Membership, Workspace
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.roles import Role

DEMO_EMAIL = "demo@upchatz.local"
DEMO_PASSWORD = "upchatz-demo"  # noqa: S105 - local demo login, DEBUG only
DEMO_FULL_NAME = "Demo Owner"
DEMO_WORKSPACE_SLUG = "demo"
DEMO_WORKSPACE_NAME = "Demo Business"
DEMO_WABA_ID = "199900000000001"
DEMO_PHONE_NUMBER_ID = "299900000000001"
DEMO_PHONE_E164 = "+919000000001"
DEMO_DISPLAY_PHONE_NUMBER = "+91 90000 00001"
# Placeholder, not a Meta token: API calls with it fail against the real Graph API.
DEMO_ACCESS_TOKEN = "demo-placeholder-token-not-valid"  # noqa: S105

Seeder = Callable[[Workspace], object]


def collect_demo_seeders(installed_apps) -> list[tuple[str, Seeder]]:
    """``(app_name, seed)`` for each local app with ``demo.py`` defining ``seed``, in order."""
    seeders = []
    for app_name in installed_apps:
        if not app_name.startswith("apps."):
            continue
        module_name = f"{app_name}.demo"
        if importlib.util.find_spec(module_name) is None:
            continue
        seed = getattr(importlib.import_module(module_name), "seed", None)
        if seed is None:
            continue
        if not callable(seed):
            raise CommandError(f"{module_name}.seed must be callable.")
        seeders.append((app_name, seed))
    return seeders


class Command(BaseCommand):
    help = "Create or update a demo workspace with a connected WhatsApp number (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEMO_EMAIL, help="Demo owner's email.")
        parser.add_argument(
            "--password",
            default=DEMO_PASSWORD,
            help="Password set when the demo owner is created (existing users keep theirs).",
        )

    def handle(self, *args, email: str, password: str, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True (never in production).")

        seeders = collect_demo_seeders(settings.INSTALLED_APPS)
        with transaction.atomic():
            user, user_created = self._user(email, password)
            workspace = self._workspace(user)
            waba = self._waba(workspace, user)
            phone_number = self._phone_number(waba)
            for app_name, seed in seeders:
                seed(workspace)
                self.stdout.write(f"Seeded {app_name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo workspace {workspace.slug} ({workspace.pk}) ready with number "
                f"{phone_number.display_phone_number}."
            )
        )
        if user_created:
            self.stdout.write(f"Log in as {user.email} with the password given by --password.")
        else:
            self.stdout.write(f"Log in as {user.email} (existing password kept).")

    def _user(self, email: str, password: str):
        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=email).first()
        if user is not None:
            return user, False
        return user_model.objects.create_user(email, password, full_name=DEMO_FULL_NAME), True

    def _workspace(self, user) -> Workspace:
        workspace, _ = Workspace.objects.get_or_create(
            slug=DEMO_WORKSPACE_SLUG,
            defaults={"name": DEMO_WORKSPACE_NAME, "created_by": user},
        )
        Membership.objects.get_or_create(
            workspace=workspace, user=user, defaults={"role": Role.OWNER}
        )
        return workspace

    def _waba(self, workspace: Workspace, user) -> WhatsAppBusinessAccount:
        waba, _ = WhatsAppBusinessAccount.objects.get_or_create(
            waba_id=DEMO_WABA_ID,
            defaults={
                "workspace": workspace,
                "name": DEMO_WORKSPACE_NAME,
                "currency": "INR",
                "access_token": DEMO_ACCESS_TOKEN,
                "status": WhatsAppBusinessAccount.Status.ACTIVE,
                "onboarding_status": WhatsAppBusinessAccount.OnboardingStatus.COMPLETED,
                "connected_by": user,
            },
        )
        if waba.workspace_id != workspace.pk:
            raise CommandError(f"WABA {DEMO_WABA_ID} belongs to another workspace.")
        return waba

    def _phone_number(self, waba: WhatsAppBusinessAccount) -> PhoneNumber:
        has_default = PhoneNumber.objects.filter(
            workspace_id=waba.workspace_id, is_default=True
        ).exists()
        phone_number, _ = PhoneNumber.objects.get_or_create(
            phone_number_id=DEMO_PHONE_NUMBER_ID,
            defaults={
                "waba": waba,
                "workspace_id": waba.workspace_id,
                "display_phone_number": DEMO_DISPLAY_PHONE_NUMBER,
                "phone_e164": DEMO_PHONE_E164,
                "verified_name": DEMO_WORKSPACE_NAME,
                "quality_rating": PhoneNumber.QualityRating.GREEN,
                "messaging_limit_tier": "TIER_1K",
                "registration_status": PhoneNumber.RegistrationStatus.REGISTERED,
                "is_default": not has_default,
            },
        )
        if phone_number.workspace_id != waba.workspace_id:
            raise CommandError(f"Phone number {DEMO_PHONE_NUMBER_ID} belongs to another workspace.")
        return phone_number
