from types import SimpleNamespace

import pytest
from django.conf import settings

from common.tests.fakes import install_module
from config import celery as celery_config
from config.celery import collect_beat_schedule

PING = {"task": "fakeapp.ping", "schedule": 60.0}
CLEANUP = {"task": "otherapp.delete_old_rows", "schedule": 3600.0}


def test_merges_entries_from_every_app(monkeypatch):
    install_module(monkeypatch, "apps.fakeapp", package=True)
    install_module(monkeypatch, "apps.fakeapp.schedules", BEAT_SCHEDULE={"fakeapp-ping": PING})
    install_module(monkeypatch, "apps.otherapp", package=True)
    install_module(
        monkeypatch, "apps.otherapp.schedules", BEAT_SCHEDULE={"otherapp-cleanup": CLEANUP}
    )
    install_module(monkeypatch, "apps.noschedules", package=True)
    install_module(monkeypatch, "apps.emptyschedules", package=True)
    install_module(monkeypatch, "apps.emptyschedules.schedules")  # no BEAT_SCHEDULE

    schedule = collect_beat_schedule(
        ["apps.fakeapp", "apps.noschedules", "apps.emptyschedules", "apps.otherapp"]
    )

    assert schedule == {"fakeapp-ping": PING, "otherapp-cleanup": CLEANUP}


def test_ignores_apps_outside_the_apps_package(monkeypatch):
    install_module(monkeypatch, "thirdparty", package=True)
    install_module(monkeypatch, "thirdparty.schedules", BEAT_SCHEDULE={"thirdparty-job": PING})

    assert collect_beat_schedule(["django.contrib.auth", "thirdparty", "common"]) == {}


def test_duplicate_entry_names_raise(monkeypatch):
    install_module(monkeypatch, "apps.first", package=True)
    install_module(monkeypatch, "apps.first.schedules", BEAT_SCHEDULE={"shared-name": PING})
    install_module(monkeypatch, "apps.second", package=True)
    install_module(
        monkeypatch,
        "apps.second.schedules",
        BEAT_SCHEDULE={"shared-name": CLEANUP, "unique": CLEANUP},
    )

    with pytest.raises(ValueError, match=r"apps\.second\.schedules.*shared-name"):
        collect_beat_schedule(["apps.first", "apps.second"])


def test_installed_apps_collect_without_error():
    assert isinstance(collect_beat_schedule(settings.INSTALLED_APPS), dict)


def test_configured_app_has_beat_schedule_from_installed_apps():
    from config.celery import app

    schedule = app.conf.beat_schedule

    assert isinstance(schedule, dict)
    assert collect_beat_schedule(settings.INSTALLED_APPS).items() <= schedule.items()


def test_hook_merges_app_entries_under_explicit_config(monkeypatch):
    monkeypatch.setattr(
        celery_config, "collect_beat_schedule", lambda apps: {"from-app": PING, "shared": PING}
    )
    source = SimpleNamespace(beat_schedule={"shared": CLEANUP, "manual": CLEANUP})

    celery_config._load_app_schedules(sender=None, source=source)

    assert source.beat_schedule == {"from-app": PING, "shared": CLEANUP, "manual": CLEANUP}


@pytest.mark.parametrize("existing", [None, {}])
@pytest.mark.parametrize("collected", [{}, {"from-app": PING}])
def test_hook_handles_empty_config(monkeypatch, existing, collected):
    monkeypatch.setattr(celery_config, "collect_beat_schedule", lambda apps: dict(collected))
    source = SimpleNamespace(beat_schedule=existing)

    celery_config._load_app_schedules(sender=None, source=source)

    assert source.beat_schedule == collected


def test_celery_app_reads_django_settings():
    from config import celery_app
    from config.celery import app

    assert celery_app is app
    assert app.main == "project_whatsapp"
    assert app.conf.task_always_eager is True
    assert app.conf.timezone == settings.TIME_ZONE
