import sys

import pytest
from django.apps import apps

from common.apps import BaseAppConfig

LOCAL_APP_CONFIGS = [
    config
    for config in apps.get_app_configs()
    if config.name == "common" or config.name.startswith("apps.")
]


def test_local_apps_are_installed():
    assert "common" in {config.name for config in LOCAL_APP_CONFIGS}
    assert len(LOCAL_APP_CONFIGS) > 1


@pytest.mark.parametrize("app_config", LOCAL_APP_CONFIGS, ids=lambda config: config.name)
def test_local_apps_use_their_own_base_app_config(app_config):
    """Regression: importing BaseAppConfig into apps.py made Django fall back to a plain
    AppConfig, so no app's receivers.py was ever imported."""
    resolved = apps.get_app_config(app_config.label)

    assert isinstance(resolved, BaseAppConfig)
    assert type(resolved) is not BaseAppConfig


def test_common_receivers_are_imported():
    assert "common.receivers" in sys.modules


def test_base_is_never_auto_selected_but_subclasses_are():
    class ProbeConfig(BaseAppConfig):
        name = "probe"

    class OptedOutConfig(BaseAppConfig):
        name = "opted_out"
        default = False

    assert BaseAppConfig.default is False
    assert ProbeConfig.default is True
    assert OptedOutConfig.default is False
