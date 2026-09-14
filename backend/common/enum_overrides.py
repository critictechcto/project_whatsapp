"""Lazy ENUM_NAME_OVERRIDES for drf-spectacular, merged from every app.

Imported by settings, so it must not import Django or DRF at module level. Each app may add
``apps/<app>/schema_enums.py`` with ``ENUM_NAME_OVERRIDES = {"ComponentName": <choices>}`` to fix
enum naming without editing settings. ``<choices>`` is a dotted path to a ``TextChoices`` class or
a tuple of values. Component names must be unique across apps; a duplicate raises ``ValueError``.

drf-spectacular matches overrides on ``(value, label)`` pairs, so a tuple of plain values would
not match a model field whose choices carry human labels. :func:`postprocess_enum_value_fallback`
closes that gap: an enum whose values equal exactly one override's values gets that override's
name, whatever its labels. Overrides that share a value set (e.g. two GREEN/YELLOW/RED scales)
keep spectacular's label-based matching.
"""

import importlib
import importlib.util
from collections import defaultdict
from collections.abc import Iterator, Mapping, MutableMapping


class AppEnumNameOverrides(Mapping):
    def __init__(self) -> None:
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is None:
            from django.conf import settings

            self._data = collect_enum_name_overrides(settings.INSTALLED_APPS)
        return self._data

    def __getitem__(self, key: str):
        return self._load()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._load())

    def __len__(self) -> int:
        return len(self._load())


def collect_enum_name_overrides(installed_apps) -> dict:
    """Merge ``ENUM_NAME_OVERRIDES`` from ``common`` and each local app's ``schema_enums.py``."""
    data: dict = {}
    for app_name in installed_apps:
        if not (app_name == "common" or app_name.startswith("apps.")):
            continue
        module_name = f"{app_name}.schema_enums"
        if importlib.util.find_spec(module_name) is None:
            continue
        entries = getattr(importlib.import_module(module_name), "ENUM_NAME_OVERRIDES", {})
        duplicates = data.keys() & entries.keys()
        if duplicates:
            raise ValueError(
                f"Duplicate enum name overrides in {module_name}: {sorted(duplicates)}"
            )
        data.update(entries)
    return data


def _normalized_choices(choices) -> list[tuple]:
    """Same normalisation drf-spectacular applies to ENUM_NAME_OVERRIDES entries."""
    import inspect
    from enum import Enum

    from django.db.models import Choices
    from drf_spectacular.plumbing import deep_import_string

    if isinstance(choices, str):
        choices = deep_import_string(choices)
    if inspect.isclass(choices) and issubclass(choices, Choices):
        choices = choices.choices
    if inspect.isclass(choices) and issubclass(choices, Enum):
        choices = [(c.value, c.name) for c in choices]
    if callable(choices):
        choices = choices()
    normalized = []
    for choice in choices or ():
        if isinstance(choice, str) or choice is None:
            normalized.append((choice, choice))
        elif isinstance(choice[1], list | tuple):
            normalized.extend(choice[1])
        else:
            normalized.append(tuple(choice))
    return [(value, label) for value, label in normalized if value not in ("", None)]


def _value_fallback_ids() -> dict[str, str]:
    """``hash(values) -> hash((value, label) pairs)`` for overrides with a unique value set."""
    from drf_spectacular.plumbing import list_hash
    from drf_spectacular.settings import spectacular_settings

    by_values: dict[str, set[str]] = defaultdict(set)
    for choices in spectacular_settings.ENUM_NAME_OVERRIDES.values():
        pairs = _normalized_choices(choices)
        if pairs:
            by_values[list_hash([(value, value) for value, _ in pairs])].add(list_hash(pairs))
    return {values: next(iter(ids)) for values, ids in by_values.items() if len(ids) == 1}


def postprocess_enum_value_fallback(result, generator, **kwargs):
    """Point enums at a value-matching override before ``postprocess_schema_enums`` names them.

    Must run immediately before ``drf_spectacular.hooks.postprocess_schema_enums``.
    """
    from drf_spectacular.plumbing import list_hash, load_enum_name_overrides

    overrides = load_enum_name_overrides()
    fallback = _value_fallback_ids()

    def visit(node) -> None:
        if isinstance(node, MutableMapping):
            enum_id = node.get("x-spec-enum-id")
            if enum_id is not None and enum_id not in overrides and "enum" in node:
                values = [value for value in node["enum"] if value not in ("", None)]
                target = fallback.get(list_hash([(value, value) for value in values]))
                if target is not None:
                    node["x-spec-enum-id"] = target
            for value in node.values():
                visit(value)
        elif isinstance(node, list | tuple):
            for item in node:
                visit(item)

    visit(result.get("components", {}))
    return result
