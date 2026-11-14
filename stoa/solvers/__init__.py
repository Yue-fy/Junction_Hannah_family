"""Solver registry.

Add a solver: create `stoa/solvers/<yours>.py` (or a subpackage `stoa/solvers/<yours>/__init__.py`), then

    from stoa.solvers import register
    from stoa.solvers.base import BaseSolver

    @register("myname")
    class MySolver(BaseSolver):
        def solve(self, path, question): ...

`get_solver("myname", **kwargs)` imports every module under stoa.solvers once (so registration happens),
then instantiates the class with kwargs. A module that fails to import is reported, not fatal, so one
broken solver never breaks the eval for everyone else.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from typing import Callable

_REGISTRY: dict[str, type] = {}
_IMPORT_ERRORS: dict[str, str] = {}
_DISCOVERED = False


def register(name: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        if name in _REGISTRY and _REGISTRY[name] is not cls:
            print(f"[stoa.solvers] warning: solver name {name!r} registered twice; keeping the last", file=sys.stderr)
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def discover() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    for mod in pkgutil.iter_modules(__path__, prefix=__name__ + "."):
        if mod.name.rsplit(".", 1)[-1].startswith("_"):
            continue
        try:
            importlib.import_module(mod.name)
        except Exception:  # noqa: BLE001 - report and continue
            _IMPORT_ERRORS[mod.name] = traceback.format_exc(limit=3)


def available() -> list[str]:
    discover()
    return sorted(_REGISTRY)


def import_errors() -> dict[str, str]:
    discover()
    return dict(_IMPORT_ERRORS)


def get_solver(name: str, **kwargs):
    discover()
    if name not in _REGISTRY:
        msg = f"unknown solver {name!r}; available: {available()}"
        bad = [m for m in _IMPORT_ERRORS if name in m]
        if bad:
            msg += "\nimport errors:\n" + "\n".join(_IMPORT_ERRORS[m] for m in bad)
        raise KeyError(msg)
    return _REGISTRY[name](**kwargs)
