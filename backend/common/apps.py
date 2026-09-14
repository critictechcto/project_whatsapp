import importlib
import importlib.util

from django.apps import AppConfig


class BaseAppConfig(AppConfig):
    """App config for every local app: auto-imports ``<app>.receivers`` so signal handlers
    connect without editing ``apps.py``."""

    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        super().ready()
        module_name = f"{self.name}.receivers"
        if importlib.util.find_spec(module_name) is not None:
            importlib.import_module(module_name)


class CommonConfig(BaseAppConfig):
    name = "common"
    verbose_name = "Common"
