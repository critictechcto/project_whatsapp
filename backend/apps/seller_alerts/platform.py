"""The UpChatz alerts number (``PLATFORM_WA_*`` settings) and its Graph client.

The number belongs to UpChatz, so UpChatz pays for templates sent from it. While a recipient's
24-hour customer service window is open (they messaged the number recently), alerts go out as
free-form messages; the platform template is used only outside the window.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.whatsapp.client import GraphClient, get_client

PLATFORM_SETTINGS = (
    "PLATFORM_WA_WABA_ID",
    "PLATFORM_WA_PHONE_NUMBER_ID",
    "PLATFORM_WA_DISPLAY_PHONE_NUMBER",
    "PLATFORM_WA_ACCESS_TOKEN",
)
SERVICE_WINDOW = timedelta(hours=24)
TEMPLATE_LANGUAGE = "en"


def missing_platform_settings(names=PLATFORM_SETTINGS) -> list[str]:
    return [name for name in names if not getattr(settings, name, "")]


def platform_alerts_available() -> bool:
    """True only when every ``PLATFORM_WA_*`` setting is configured."""
    return not missing_platform_settings()


def platform_client() -> GraphClient:
    return get_client(settings.PLATFORM_WA_ACCESS_TOKEN)


def platform_phone_number_id() -> str:
    return settings.PLATFORM_WA_PHONE_NUMBER_ID


def window_open(last_inbound_at, now=None) -> bool:
    """Whether a phone that last messaged the platform number at ``last_inbound_at`` is still
    inside its 24-hour customer service window."""
    if last_inbound_at is None:
        return False
    now = now or timezone.now()
    return now - last_inbound_at < SERVICE_WINDOW
