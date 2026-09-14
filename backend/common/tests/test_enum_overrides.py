import pytest
from django.conf import settings

from common.enum_overrides import (
    AppEnumNameOverrides,
    collect_enum_name_overrides,
    postprocess_enum_value_fallback,
)
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


def test_duplicate_component_names_across_apps_raise(monkeypatch):
    install_module(monkeypatch, "apps.first", package=True)
    install_module(
        monkeypatch, "apps.first.schema_enums", ENUM_NAME_OVERRIDES={"SharedEnum": ("a", "b")}
    )
    install_module(monkeypatch, "apps.second", package=True)
    install_module(
        monkeypatch, "apps.second.schema_enums", ENUM_NAME_OVERRIDES={"SharedEnum": ("c",)}
    )

    with pytest.raises(ValueError, match=r"apps\.second\.schema_enums.*SharedEnum"):
        collect_enum_name_overrides(["common", "apps.first", "apps.second"])


def test_contract_apps_have_unique_override_names():
    overrides = collect_enum_name_overrides(settings.INSTALLED_APPS)

    for name in ("ConversationStatusEnum", "CampaignStatusEnum", "AutomationTriggerEnum"):
        assert name in overrides
    assert overrides["SubscriptionStatusEnum"]


def _enum_node(values, enum_id="unmatched-id"):
    return {"type": "string", "enum": values, "x-spec-enum-id": enum_id}


def test_value_fallback_renames_enums_whose_values_match_one_override(monkeypatch):
    from drf_spectacular import plumbing
    from drf_spectacular.settings import spectacular_settings

    overrides = {
        "ColorEnum": ("red", "green"),
        "RatingAEnum": [("G", "Green")],
        "RatingBEnum": [("G", "Good")],
    }
    monkeypatch.setattr(spectacular_settings, "ENUM_NAME_OVERRIDES", overrides, raising=False)
    known_id = plumbing.list_hash([("G", "Green")])
    monkeypatch.setattr(plumbing, "load_enum_name_overrides", lambda: {known_id: "RatingAEnum"})
    color = _enum_node(["red", "green", "", None])
    labelled = _enum_node(["green", "red"], enum_id=known_id)
    shared_values = _enum_node(["G"])
    no_match = _enum_node(["blue"])
    result = {
        "components": {
            "schemas": {
                "Thing": {
                    "properties": {
                        "color": color,
                        "labelled": labelled,
                        "rating": {"oneOf": [shared_values]},
                        "other": no_match,
                    }
                }
            }
        }
    }

    assert postprocess_enum_value_fallback(result, generator=None) is result

    assert color["x-spec-enum-id"] == plumbing.list_hash([("red", "red"), ("green", "green")])
    assert labelled["x-spec-enum-id"] == known_id
    assert shared_values["x-spec-enum-id"] == "unmatched-id"
    assert no_match["x-spec-enum-id"] == "unmatched-id"


def test_value_fallback_hook_runs_before_spectacular_enum_naming():
    hooks = settings.SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"]

    assert hooks == [
        "common.enum_overrides.postprocess_enum_value_fallback",
        "drf_spectacular.hooks.postprocess_schema_enums",
    ]
