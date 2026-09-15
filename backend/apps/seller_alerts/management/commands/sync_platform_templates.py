"""``manage.py sync_platform_templates``: create and update the seller alert templates in
UpChatz's WABA."""

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from apps.seller_alerts.platform import missing_platform_settings
from apps.seller_alerts.platform_templates import sync_platform_templates
from apps.whatsapp.client import GraphAPIError


class Command(BaseCommand):
    help = (
        "Create the platform templates upc_seller_verify, upc_new_order and upc_order_attention "
        "in PLATFORM_WA_WABA_ID when missing, edit the ones that differ from their definition "
        "where Meta allows it, and print their Meta review statuses. Safe to re-run."
    )

    def handle(self, *args, **options):
        missing = missing_platform_settings(("PLATFORM_WA_WABA_ID", "PLATFORM_WA_ACCESS_TOKEN"))
        if missing:
            raise CommandError(f"Set {', '.join(missing)} before syncing the platform templates.")
        try:
            results = sync_platform_templates()
        except GraphAPIError as exc:
            raise CommandError(f"Meta rejected the request: {exc}") from exc
        except ValidationError as exc:
            raise CommandError(f"A platform template definition is invalid: {exc.detail}") from exc

        for result in results:
            action = f"{result.action}: {result.note}" if result.note else result.action
            line = (
                f"{result.name} ({result.language}, {result.category or '?'}): "
                f"{result.status} [{action}]"
            )
            style = self.style.WARNING if result.action == "outdated" else self.style.SUCCESS
            self.stdout.write(style(line))
