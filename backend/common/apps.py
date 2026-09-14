import importlib
import importlib.util

from django.apps import AppConfig


class BaseAppConfig(AppConfig):
    """App config for every local app: auto-imports ``<app>.receivers`` so signal handlers
    connect without editing ``apps.py``."""

    # Every apps.py imports this class, and Django only auto-selects an app's config when exactly
    # one eligible AppConfig subclass is in the module. Exclude the base; subclasses opt back in.
    default = False
    default_auto_field = "django.db.models.BigAutoField"

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if "default" not in cls.__dict__:
            cls.default = True

    def ready(self) -> None:
        super().ready()
        module_name = f"{self.name}.receivers"
        if importlib.util.find_spec(module_name) is not None:
            importlib.import_module(module_name)


class CommonConfig(BaseAppConfig):
    name = "common"
    verbose_name = "Common"
