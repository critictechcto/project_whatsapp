"""Helpers for tests that need importable modules which don't exist on disk."""

import sys
import types
from importlib.machinery import ModuleSpec


def install_module(monkeypatch, name: str, *, package: bool = False, **attrs) -> types.ModuleType:
    """Put a module named ``name`` in ``sys.modules`` for the duration of the test.

    ``importlib.util.find_spec`` returns ``__spec__`` for modules already in ``sys.modules``, so
    code that probes optional submodules (``apps.<app>.schedules``) finds these fakes. A
    ``package`` gets an empty ``__path__``, so probing a submodule that isn't installed returns
    ``None`` instead of raising.
    """
    module = types.ModuleType(name)
    module.__spec__ = ModuleSpec(name, loader=None, is_package=package)
    if package:
        module.__path__ = []
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module
