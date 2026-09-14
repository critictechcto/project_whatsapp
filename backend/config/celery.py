import importlib
import importlib.util
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("upchatz")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


def collect_beat_schedule(installed_apps) -> dict:
    """Merge ``BEAT_SCHEDULE`` dicts from each local app's optional ``schedules.py``.

    ``schedules.py`` must stay import-light (celery.schedules only, no models) because it is
    loaded while Celery configures itself. Entry names must be unique across apps.
    """
    schedule: dict = {}
    for app_name in installed_apps:
        if not app_name.startswith("apps."):
            continue
        module_name = f"{app_name}.schedules"
        if importlib.util.find_spec(module_name) is None:
            continue
        entries = getattr(importlib.import_module(module_name), "BEAT_SCHEDULE", {})
        duplicates = schedule.keys() & entries.keys()
        if duplicates:
            raise ValueError(
                f"Duplicate Celery beat entries in {module_name}: {sorted(duplicates)}"
            )
        schedule.update(entries)
    return schedule


@app.on_after_configure.connect
def _load_app_schedules(sender, source, **kwargs):
    from django.conf import settings

    source.beat_schedule = {
        **collect_beat_schedule(settings.INSTALLED_APPS),
        **(source.beat_schedule or {}),
    }
