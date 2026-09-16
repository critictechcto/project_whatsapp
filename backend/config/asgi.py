import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

from django.conf import settings  # noqa: E402
from django.core.exceptions import ImproperlyConfigured  # noqa: E402

if getattr(settings, "BUILD_ONLY", False):
    raise ImproperlyConfigured("config.settings.build is for collectstatic only; use prod.")

from channels.routing import ProtocolTypeRouter  # noqa: E402

from common.ws_auth import websocket_application  # noqa: E402
from config.routing import websocket_urlpatterns  # noqa: E402

# WebSockets: Origin must be in WS_ALLOWED_ORIGINS, then a single-use ticket authenticates the
# connection (common.ws_auth), then routes collected from each app's routing.py handle it.
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": websocket_application(websocket_urlpatterns),
    }
)
