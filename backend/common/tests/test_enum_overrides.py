import pytest
from django.conf import settings

from common.enum_overrides import AppEnumNameOverrides
from common.tests.fakes import install_module


def test_includes_role_enum_from_common():
    overrides = AppEnumNameOverrides()

    assert overrides["RoleEnum"] == "common.roles.Role"
    assert "RoleEnum" in overrides
    assert dict(overrides)["RoleEnum"] == "common.roles.Role"


def test_mapping_protocol():
    overrides = AppEnumNameOverrides()

    assert len(overrides) == len(list(overrides)) >= 1
    assert set(iter(overrides)) == set(overrides.keys())
    with pytest.raises(KeyError):
        overrides["NoSuchEnum"]


def test_loads_lazily():
    overrides = AppEnumNameOverrides()
    assert overrides._data is None

    len(overrides)

    assert overrides._data is not None


def test_merges_local_apps_and_ignores_others(monkeypatch):
    install_module(monkeypatch, "apps.fakeenums", package=True)
    install_module(
        monkeypatch,
        "apps.fakeenums.schema_enums",
        ENUM_NAME_OVERRIDES={"FakeStatusEnum": "apps.fakeenums.models.Status"},
    )
    install_module(monkeypatch, "apps.noenums", package=True)
    install_module(monkeypatch, "apps.noattr", package=True)
    install_module(monkeypatch, "apps.noattr.schema_enums")
    install_module(monkeypatch, "thirdparty", package=True)
    install_module(monkeypatch, "thirdparty.schema_enums", ENUM_NAME_OVERRIDES={"ThirdEnum": "x.Y"})
    monkeypatch.setattr(
        settings,
        "INSTALLED_APPS",
        [
            "django.contrib.auth",
            "thirdparty",
            "common",
            "apps.fakeenums",
            "apps.noenums",
            "apps.noattr",
        ],
    )

    assert dict(AppEnumNameOverrides()) == {
        "RoleEnum": "common.roles.Role",
        "FakeStatusEnum": "apps.fakeenums.models.Status",
    }


def test_spectacular_settings_use_app_overrides():
    assert isinstance(settings.SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"], AppEnumNameOverrides)
