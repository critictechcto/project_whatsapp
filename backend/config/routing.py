"""WebSocket routes, collected from each local app's optional ``routing.py``."""

import importlib
import importlib.util

from django.conf import settings


def collect_websocket_urlpatterns(installed_apps) -> list:
    patterns: list = []
    for app_name in installed_apps:
        if not app_name.startswith("apps."):
            continue
        module_name = f"{app_name}.routing"
        if importlib.util.find_spec(module_name) is None:
            continue
        patterns.extend(getattr(importlib.import_module(module_name), "websocket_urlpatterns", []))
    return patterns


websocket_urlpatterns = collect_websocket_urlpatterns(settings.INSTALLED_APPS)
