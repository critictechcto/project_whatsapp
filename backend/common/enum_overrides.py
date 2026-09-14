"""Lazy ENUM_NAME_OVERRIDES for drf-spectacular, merged from every app.

Imported by settings, so it must not import Django or DRF at module level. Each app may add
``apps/<app>/schema_enums.py`` with ``ENUM_NAME_OVERRIDES = {"ComponentName": "dotted.Choices"}``
to fix enum naming collisions without editing settings.
"""

import importlib
import importlib.util
from collections.abc import Iterator, Mapping


class AppEnumNameOverrides(Mapping):
    def __init__(self) -> None:
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is None:
            from django.conf import settings

            data: dict = {}
            for app_name in settings.INSTALLED_APPS:
                if not (app_name == "common" or app_name.startswith("apps.")):
                    continue
                module_name = f"{app_name}.schema_enums"
                if importlib.util.find_spec(module_name) is None:
                    continue
                data.update(
                    getattr(importlib.import_module(module_name), "ENUM_NAME_OVERRIDES", {})
                )
            self._data = data
        return self._data

    def __getitem__(self, key: str):
        return self._load()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._load())

    def __len__(self) -> int:
        return len(self._load())
