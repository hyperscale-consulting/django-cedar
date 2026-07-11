"""Cedar policy-based authorization for Django."""

from __future__ import annotations

import importlib
from typing import Any

__all__: list[str] = ["Authz", "Entity", "EntityRef", "create_authz"]

# PEP 562 lazy exports: Django imports this package during app loading, when
# models are not yet ready — so django_cedar.authz (which imports auth models)
# must not be imported until an attribute is actually accessed.


def __getattr__(name: str) -> Any:
    if name in __all__:
        return getattr(importlib.import_module("django_cedar.authz"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
