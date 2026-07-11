# django-cedar Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the `django_cedar` app from `../hyperscale/app-studio/django_cedar` into a standalone open-source package published to PyPI as `django-cedar`.

**Architecture:** A plain Python library (`src/django_cedar/`) usable via imports alone, plus an optional Django `AppConfig` that registers system checks when the package is added to `INSTALLED_APPS`. The `Authz` engine wraps `cedarpy.is_authorized`; settings-driven factory `create_authz()` loads policies and pluggable providers; CBV mixins enforce authorization in `dispatch()`.

**Tech Stack:** Python 3.12+, Django 5.2/6.0, cedarpy, uv (`uv_build` backend), ruff, pyright, pytest + pytest-django, pre-commit, GitHub Actions with PyPI Trusted Publishing.

**Spec:** `docs/superpowers/specs/2026-07-11-django-cedar-extraction-design.md`

## Global Constraints

- `requires-python = ">=3.12"`; runtime deps exactly: `django>=5.2`, `cedarpy>=4.8.1`.
- License: Apache-2.0.
- Import style: one `from x import y` per line (ruff isort `force-single-line = true`, `order-by-type = false`).
- `ruff check`, `ruff format --check`, and `pyright` (basic mode) must pass before every commit.
- All GitHub Actions pinned to full commit SHAs with a `# vN` trailing comment.
- All commands run via `uv run` / `uvx` from the repo root `/Users/acaine/src/django-cedar`.
- Commits are GPG-signed automatically (repo-local git config already set — do not change git config).
- End every commit message with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- The source being extracted lives at `/Users/acaine/src/hyperscale/app-studio/django_cedar/` — read it if a task needs cross-checking, never modify it.
- New Cedar-specific Django settings are exactly: `CEDAR_POLICY_PATH`, `CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS`, `CEDAR_CONTEXT_PROVIDERS`.

---

### Task 1: Project scaffold (uv, pyproject, license)

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `src/django_cedar/__init__.py` (empty for now)
- Create: `src/django_cedar/py.typed` (empty marker)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: an installable package skeleton importable as `django_cedar`; `[dependency-groups] dev` with pytest/pytest-django/pytest-cov/ruff/pyright; tool config for ruff/pyright/pytest used by all later tasks.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "django-cedar"
version = "0.1.0"
description = "Cedar policy-based authorization for Django"
readme = "README.md"
license = "Apache-2.0"
license-files = ["LICENSE"]
authors = [{ name = "Andy Caine", email = "andy@hyperscale.consulting" }]
requires-python = ">=3.12"
dependencies = [
    "cedarpy>=4.8.1",
    "django>=5.2",
]
keywords = ["django", "cedar", "authorization", "authz", "policy"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Framework :: Django",
    "Framework :: Django :: 5.2",
    "Framework :: Django :: 6.0",
    "Intended Audience :: Developers",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Topic :: Security",
]

[project.urls]
Homepage = "https://github.com/hyperscale-consulting/django-cedar"
Changelog = "https://github.com/hyperscale-consulting/django-cedar/blob/main/CHANGELOG.md"
Issues = "https://github.com/hyperscale-consulting/django-cedar/issues"

[dependency-groups]
dev = [
    "pyright>=1.1.400",
    "pytest>=8.0",
    "pytest-cov>=6.0",
    "pytest-django>=4.9",
    "ruff>=0.15.21",
]

[build-system]
requires = ["uv_build>=0.9,<1.0"]
build-backend = "uv_build"

[tool.ruff]
fix = true
show-fixes = true
output-format = "full"

[tool.ruff.lint]
select = [
    "B",  # flake8-bugbear
    "E",  # pycodestyle error
    "F",  # pyflakes
    "I",  # isort
    "UP",  # pyupgrade
    "W",  # pycodestyle warning
]

[tool.ruff.lint.isort]
force-single-line = true
order-by-type = false

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "basic"
include = ["src", "tests"]
venvPath = "."
venv = ".venv"

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "tests.settings"
testpaths = ["tests"]
```

- [ ] **Step 2: Write `.python-version`**

```
3.12
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
dist/
.pytest_cache/
.ruff_cache/
*.egg-info/
.coverage
htmlcov/
```

- [ ] **Step 4: Fetch the Apache-2.0 license text**

Run: `curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE`
Expected: `LICENSE` exists, starts with "Apache License" and "Version 2.0, January 2004".

Note: Apache-2.0 does not require filling in a copyright line in the LICENSE file itself — use it verbatim.

- [ ] **Step 5: Create the package skeleton and a placeholder README**

```bash
mkdir -p src/django_cedar
touch src/django_cedar/__init__.py src/django_cedar/py.typed
printf '# django-cedar\n\nCedar policy-based authorization for Django. Full README lands in a later task.\n' > README.md
```

- [ ] **Step 6: Sync and verify the package builds and imports**

Run:
```bash
uv sync
uv build
uv run python -c "import django_cedar; print('ok')"
```
Expected: `uv sync` creates `.venv` and `uv.lock`; `uv build` produces `dist/django_cedar-0.1.0.tar.gz` and `dist/django_cedar-0.1.0-py3-none-any.whl`; import prints `ok`.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check .
uv run ruff format .
git add pyproject.toml .python-version .gitignore LICENSE README.md src uv.lock
git commit -m "feat: scaffold django-cedar uv project

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: `pyproject.toml` + `uv.lock` from Task 1 (the `uv-lock` hook validates it)
- Produces: git hooks that run on every later commit in this plan.

- [ ] **Step 1: Write `.pre-commit-config.yaml`** (same frozen revs as app-studio)

```yaml
repos:
  # Keep in lockstep with the ruff version in uv.lock (uv lock --upgrade-package ruff).
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: 01a675ea018f2fb714478a5ffb83fcea8374bb06  # frozen: v0.15.21
    hooks:
      - id: ruff-check
      - id: ruff-format
  - repo: https://github.com/astral-sh/uv-pre-commit
    rev: d9fca3320346514799461a80b0753eb45d707d46  # frozen: 0.11.28
    hooks:
      - id: uv-lock
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: 3e8a8703264a2f4a69428a0aa4dcb512790b2c8c  # frozen: v6.0.0
    hooks:
      - id: check-merge-conflict
      - id: debug-statements
      - id: fix-byte-order-marker
      - id: trailing-whitespace
      - id: end-of-file-fixer
```

- [ ] **Step 2: Install hooks and run against all files**

Run:
```bash
uvx pre-commit install
uvx pre-commit run --all-files
```
Expected: all hooks pass (trailing-whitespace / end-of-file-fixer may auto-fix files on first run — if so, `git add` the fixes and re-run until clean).

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: add pre-commit hooks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Test harness

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/settings.py`
- Create: `tests/policies.cedar`
- Create: `tests/test_packaging.py`

**Interfaces:**
- Consumes: package skeleton from Task 1
- Produces: `tests.settings` (Django settings module with `BASE_DIR = tests/`, `CEDAR_POLICY_PATH = "policies.cedar"`) used by all later test tasks; a passing pytest run.

- [ ] **Step 1: Write `tests/settings.py`**

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "test-only-secret-key"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django_cedar",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CEDAR_POLICY_PATH = "policies.cedar"
```

- [ ] **Step 2: Write `tests/policies.cedar`**

```
permit(principal, action, resource);
```

- [ ] **Step 3: Write the failing packaging test in `tests/test_packaging.py`**

```python
from __future__ import annotations

import os
import subprocess
import sys


def test_import_without_django_settings():
    """The package must be importable before django.setup() / settings config.

    Django imports the package during app loading, when models are not yet
    ready — so the top-level package must not import Django models eagerly.
    """
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    result = subprocess.run(
        [sys.executable, "-c", "import django_cedar"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
```

Also create the empty `tests/__init__.py`:

```bash
touch tests/__init__.py
```

- [ ] **Step 4: Run the test suite**

Run: `uv run pytest -v`
Expected: PASS (1 test) — `__init__.py` is still empty so the import is trivially safe. This test exists now so every later task that touches `__init__.py` keeps it lazy.

- [ ] **Step 5: Commit**

```bash
git add tests
git commit -m "test: add pytest-django harness and packaging import test

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Authz core (`Entity`, `EntityRef`, entity construction, `Authz` with context providers)

**Files:**
- Create: `src/django_cedar/authz.py`
- Create: `tests/test_authz.py`

**Interfaces:**
- Consumes: test harness from Task 3
- Produces: `django_cedar.authz` module with:
  - `EntityRef(type: str, id: str)` frozen dataclass with `to_dict() -> dict`
  - `Entity(ref: EntityRef, attrs: dict[str, Any] = {}, parents: set[EntityRef] = set())` frozen dataclass with `Entity.create(type: str, id: str) -> Entity` and `to_dict() -> dict`
  - `Authz(policies: str, principal_attribute_providers: list[Any] | None = None, context_providers: list[Any] | None = None)` with `authorize(user, action: str, resource, *, context: dict[str, Any] | None = None) -> None` (raises `django.core.exceptions.PermissionDenied` on deny)
  - helpers `_make_entities`, `_make_principal_entities`, `_deep_merge` (used by tests)
  - Context providers implement `get_context(user, action, resource) -> dict` where `action` is the raw action string and `resource` the raw Django model (or None); results deep-merge in list order, then the per-call `context=` merges last and wins.

This is the app-studio `authz.py` with four changes: `Model` renamed to `Entity`; the hardcoded `ALLOW_SELF_SIGNUP` context removed; `context_providers` added to `Authz`; all settings-loading functions deferred to Task 5.

- [ ] **Step 1: Write the failing tests in `tests/test_authz.py`**

This is the ported app-studio `django_cedar/tests/test_authz.py` with: `Model` → `Entity` in imports and test bodies; the two `ALLOW_SELF_SIGNUP` tests (`test_self_signup_context`, `test_self_signup_context_denied`) replaced by the `TestContextProviders` class.

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.core.exceptions import PermissionDenied

from django_cedar.authz import _deep_merge
from django_cedar.authz import _make_entities
from django_cedar.authz import _make_principal_entities
from django_cedar.authz import Authz
from django_cedar.authz import Entity
from django_cedar.authz import EntityRef

PERMIT_ALL = "permit(principal, action, resource);"
DENY_ALL = "forbid(principal, action, resource);"


def _make_mock_user(pk=1, is_staff=False, is_superuser=False, groups=None):
    user = MagicMock()
    user.pk = pk
    user.is_authenticated = True
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.groups.all.return_value = groups or []
    return user


def _make_mock_resource(class_name, pk=1):
    """Create a mock resource that isn't an AbstractUser and has a proper class name."""

    class FakeModel:
        pass

    FakeModel.__name__ = class_name
    obj = FakeModel()
    obj.pk = pk
    return obj


def _make_mock_group(pk, name):
    group = MagicMock()
    group.pk = pk
    group.name = name
    return group


class TestAuthzAuthorize:
    def test_permit_all_allows_request(self):
        authz = Authz(policies=PERMIT_ALL)
        user = _make_mock_user()
        authz.authorize(user, "DoSomething", None)

    def test_deny_all_raises_permission_denied(self):
        authz = Authz(policies=DENY_ALL)
        user = _make_mock_user()
        with pytest.raises(PermissionDenied):
            authz.authorize(user, "DoSomething", None)

    def test_empty_policy_denies(self):
        authz = Authz(policies="")
        user = _make_mock_user()
        with pytest.raises(PermissionDenied):
            authz.authorize(user, "DoSomething", None)

    def test_anonymous_user_uses_anonymous_principal(self):
        policy = 'permit(principal == Anonymous::"guest", action, resource);'
        authz = Authz(policies=policy)
        authz.authorize(None, "DoSomething", None)

    def test_anonymous_user_denied_when_policy_requires_user(self):
        policy = "permit(principal is User, action, resource);"
        authz = Authz(policies=policy)
        with pytest.raises(PermissionDenied):
            authz.authorize(None, "DoSomething", None)

    def test_authenticated_user_uses_user_principal(self):
        policy = 'permit(principal == User::"42", action, resource);'
        authz = Authz(policies=policy)
        user = _make_mock_user(pk=42)
        authz.authorize(user, "DoSomething", None)

    def test_none_resource_uses_global(self):
        policy = 'permit(principal, action, resource == System::"global");'
        authz = Authz(policies=policy)
        user = _make_mock_user()
        authz.authorize(user, "DoSomething", None)

    def test_model_resource_uses_classname_and_pk(self):
        policy = 'permit(principal, action, resource == Widget::"7");'
        authz = Authz(policies=policy)
        user = _make_mock_user()

        resource = _make_mock_resource("Widget", pk=7)
        authz.authorize(user, "DoSomething", resource)

    def test_action_name_formatted_correctly(self):
        policy = 'permit(principal, action == Action::"ViewWidget", resource);'
        authz = Authz(policies=policy)
        user = _make_mock_user()
        authz.authorize(user, "ViewWidget", None)

    def test_custom_context_merged(self):
        policy = """
        permit(principal, action, resource)
        when { context.custom.flag };
        """
        authz = Authz(policies=policy)
        user = _make_mock_user()
        authz.authorize(user, "DoSomething", None, context={"custom": {"flag": True}})

    def test_custom_context_denied_when_false(self):
        policy = """
        permit(principal, action, resource)
        when { context.custom.flag };
        """
        authz = Authz(policies=policy)
        user = _make_mock_user()
        with pytest.raises(PermissionDenied):
            authz.authorize(
                user, "DoSomething", None, context={"custom": {"flag": False}}
            )

    def test_principal_attribute_providers_called(self):
        provider = MagicMock()
        provider.get_attributes.return_value = {"role": "admin"}
        policy = """
        permit(principal, action, resource)
        when { principal.role == "admin" };
        """
        authz = Authz(policies=policy, principal_attribute_providers=[provider])
        user = _make_mock_user()
        authz.authorize(user, "DoSomething", None)
        provider.get_attributes.assert_called_once_with(user)


class _StaticContextProvider:
    def __init__(self, context):
        self._context = context

    def get_context(self, user, action, resource):
        return self._context


class TestContextProviders:
    def test_provider_context_used(self):
        policy = """
        permit(principal, action, resource)
        when { context.allow.self_signup };
        """
        provider = _StaticContextProvider({"allow": {"self_signup": True}})
        authz = Authz(policies=policy, context_providers=[provider])
        authz.authorize(_make_mock_user(), "DoSomething", None)

    def test_provider_context_denied(self):
        policy = """
        permit(principal, action, resource)
        when { context.allow.self_signup };
        """
        provider = _StaticContextProvider({"allow": {"self_signup": False}})
        authz = Authz(policies=policy, context_providers=[provider])
        with pytest.raises(PermissionDenied):
            authz.authorize(_make_mock_user(), "DoSomething", None)

    def test_providers_merge_in_order_later_wins(self):
        policy = """
        permit(principal, action, resource)
        when { context.stage == "second" };
        """
        first = _StaticContextProvider({"stage": "first"})
        second = _StaticContextProvider({"stage": "second"})
        authz = Authz(policies=policy, context_providers=[first, second])
        authz.authorize(_make_mock_user(), "DoSomething", None)

    def test_call_context_wins_over_providers(self):
        policy = """
        permit(principal, action, resource)
        when { context.stage == "call" };
        """
        provider = _StaticContextProvider({"stage": "provider"})
        authz = Authz(policies=policy, context_providers=[provider])
        authz.authorize(
            _make_mock_user(), "DoSomething", None, context={"stage": "call"}
        )

    def test_provider_receives_user_action_and_resource(self):
        provider = MagicMock()
        provider.get_context.return_value = {}
        authz = Authz(policies=PERMIT_ALL, context_providers=[provider])
        user = _make_mock_user()
        resource = _make_mock_resource("Widget", pk=3)
        authz.authorize(user, "DoSomething", resource)
        provider.get_context.assert_called_once_with(user, "DoSomething", resource)


class TestMakePrincipalEntities:
    def test_authenticated_user_entity(self):
        user = _make_mock_user(pk=5, is_staff=True, is_superuser=False)
        entities = _make_principal_entities(user, principal_attribute_providers=[])
        entity_list = list(entities)
        user_entity = next(e for e in entity_list if e.ref.type == "User")
        assert user_entity.ref.id == "5"
        assert user_entity.attrs["is_staff"] is True
        assert user_entity.attrs["is_superuser"] is False
        assert user_entity.attrs["id"] == "5"

    def test_anonymous_user_entity(self):
        entities = _make_principal_entities(None, principal_attribute_providers=[])
        entity_list = list(entities)
        assert len(entity_list) == 1
        assert entity_list[0].ref.type == "Anonymous"
        assert entity_list[0].ref.id == "guest"

    def test_unauthenticated_user_entity(self):
        user = MagicMock()
        user.is_authenticated = False
        entities = _make_principal_entities(user, principal_attribute_providers=[])
        entity_list = list(entities)
        assert len(entity_list) == 1
        assert entity_list[0].ref.type == "Anonymous"

    def test_user_groups_become_parent_entities(self):
        group = _make_mock_group(pk=10, name="editors")
        user = _make_mock_user(pk=1, groups=[group])
        entities = _make_principal_entities(user, principal_attribute_providers=[])
        entity_list = list(entities)

        user_entity = next(e for e in entity_list if e.ref.type == "User")
        assert EntityRef("Group", "editors") in user_entity.parents

        group_entity = next(e for e in entity_list if e.ref.type == "Group")
        assert group_entity.ref.id == "editors"
        assert group_entity.attrs["id"] == "10"


class TestMakeEntities:
    def test_model_entity(self):
        resource = _make_mock_resource("Widget", pk=42)
        entities = _make_entities(resource, principal_attribute_providers=[])
        entity_list = list(entities)
        assert len(entity_list) == 1
        assert entity_list[0].ref.type == "Widget"
        assert entity_list[0].ref.id == "42"
        assert entity_list[0].attrs["id"] == "42"

    def test_model_with_authz_fields(self):
        resource = _make_mock_resource("Report", pk=1)
        resource.authz_fields = lambda: {"status": "draft", "org_id": "99"}
        entities = _make_entities(resource, principal_attribute_providers=[])
        entity_list = list(entities)
        assert entity_list[0].attrs["status"] == "draft"
        assert entity_list[0].attrs["org_id"] == "99"
        assert entity_list[0].attrs["id"] == "1"

    def test_related_entities_included_transitively(self):
        related = _make_mock_resource("Org", pk=9)
        resource = _make_mock_resource("Report", pk=1)
        resource.authz_related_entities = lambda: [related]
        entities = _make_entities(resource, principal_attribute_providers=[])
        types = {e.ref.type for e in entities}
        assert types == {"Report", "Org"}


class TestEntityRef:
    def test_to_dict(self):
        ref = EntityRef("User", "42")
        assert ref.to_dict() == {"type": "User", "id": "42"}


class TestEntity:
    def test_create(self):
        entity = Entity.create("User", "1")
        assert entity.ref.type == "User"
        assert entity.ref.id == "1"

    def test_to_dict(self):
        entity = Entity(
            EntityRef("User", "1"),
            attrs={"is_staff": True},
            parents={EntityRef("Group", "admin")},
        )
        d = entity.to_dict()
        assert d["uid"] == {"__entity": {"type": "User", "id": "1"}}
        assert d["attrs"] == {"is_staff": True}
        assert d["parents"] == [{"type": "Group", "id": "admin"}]

    def test_equality_by_ref(self):
        e1 = Entity(EntityRef("User", "1"), attrs={"a": 1})
        e2 = Entity(EntityRef("User", "1"), attrs={"b": 2})
        assert e1 == e2

    def test_hash_by_ref(self):
        e1 = Entity(EntityRef("User", "1"), attrs={"a": 1})
        e2 = Entity(EntityRef("User", "1"), attrs={"b": 2})
        assert hash(e1) == hash(e2)
        assert len({e1, e2}) == 1


class TestDeepMerge:
    def test_simple_merge(self):
        dst = {"a": 1}
        result = _deep_merge(dst, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_merge(self):
        dst = {"a": {"x": 1, "y": 2}}
        result = _deep_merge(dst, {"a": {"y": 3, "z": 4}})
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_overwrite_non_dict(self):
        dst = {"a": 1}
        result = _deep_merge(dst, {"a": {"nested": True}})
        assert result == {"a": {"nested": True}}

    def test_mutates_dst(self):
        dst = {"a": 1}
        result = _deep_merge(dst, {"b": 2})
        assert dst is result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_authz.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'django_cedar.authz'`.

- [ ] **Step 3: Write `src/django_cedar/authz.py`**

```python
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from cedarpy import is_authorized
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db.models import Model as DjangoModel

logger = logging.getLogger(__name__)


class Authz:
    def __init__(
        self,
        policies: str,
        principal_attribute_providers: list[Any] | None = None,
        context_providers: list[Any] | None = None,
    ):
        self.policies = policies
        self.principal_attribute_providers = principal_attribute_providers or []
        self.context_providers = context_providers or []

    def authorize(
        self,
        user: AbstractUser | None,
        action: str,
        resource: DjangoModel | None,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        entities = _make_principal_entities(
            user, principal_attribute_providers=self.principal_attribute_providers
        )
        if resource:
            entities.update(
                _make_entities(resource, self.principal_attribute_providers)
            )
        entity_dicts = [e.to_dict() for e in entities]
        cedar_resource = (
            resource
            and f'{type(resource).__name__}::"{resource.pk}"'
            or 'System::"global"'
        )
        principal = 'Anonymous::"guest"'
        if user and user.is_authenticated:
            principal = f'User::"{str(user.pk)}"'
        cedar_context: dict[str, Any] = {}
        for provider in self.context_providers:
            _deep_merge(cedar_context, provider.get_context(user, action, resource))
        if context:
            _deep_merge(cedar_context, context)
        authz_request = dict(
            principal=principal,
            action=f'Action::"{action}"',
            resource=cedar_resource,
            context=cedar_context,
        )
        logger.debug(f"Entities:\n {json.dumps(entity_dicts, indent=2)}")
        logger.debug(f"AuthRequest:\n {json.dumps(authz_request, indent=2)}")
        authz_result = is_authorized(authz_request, self.policies, entity_dicts)
        if not authz_result.allowed:
            logger.debug(f"AuthzResult errors: {authz_result.diagnostics.errors}")
            logger.info(f"Authz denied: {authz_request}")
            raise PermissionDenied("Forbidden")


@dataclass(frozen=True)
class EntityRef:
    type: str
    id: str

    def to_dict(self) -> dict:
        return dict(type=self.type, id=self.id)


@dataclass(frozen=True)
class Entity:
    ref: EntityRef
    attrs: dict[str, Any] = field(default_factory=dict)
    parents: set[EntityRef] = field(default_factory=set)

    def __hash__(self):
        return hash((self.ref.type, self.ref.id))

    def __eq__(self, value):
        return isinstance(value, Entity) and self.ref == value.ref

    @staticmethod
    def create(type: str, id: str) -> Entity:
        return Entity(EntityRef(type, id))

    def to_dict(self) -> dict:
        return {
            "uid": {"__entity": self.ref.to_dict()},
            "attrs": self.attrs,
            "parents": [p.to_dict() for p in self.parents],
        }


def _make_user_entities(
    user: AbstractUser, principal_attribute_providers: list[Any]
) -> set[Entity]:
    result = set()
    attrs = {
        "id": str(user.pk),
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }
    for provider in principal_attribute_providers:
        attrs.update(provider.get_attributes(user))
        if hasattr(provider, "get_entities"):
            result.update(provider.get_entities(user))

    result.add(
        Entity(
            EntityRef("User", str(user.pk)),
            attrs=attrs,
            parents={EntityRef("Group", group.name) for group in user.groups.all()},
        )
    )
    for group in user.groups.all():
        result.add(
            Entity(
                EntityRef("Group", group.name),
                attrs={"id": str(group.pk)},
            )
        )
    return result


def _make_principal_entities(
    user: AbstractUser | None, principal_attribute_providers: list[Any]
) -> set[Entity]:
    if not user or not user.is_authenticated:
        return {Entity(EntityRef("Anonymous", "guest"))}

    return _make_user_entities(user, principal_attribute_providers)


def _make_entities(
    entity: Any, principal_attribute_providers: list[Any]
) -> set[Entity]:
    if isinstance(entity, AbstractUser):
        return _make_principal_entities(entity, principal_attribute_providers)

    result = set()

    attrs: dict[str, Any] = {}
    authz_fields = getattr(entity, "authz_fields", None)
    if callable(authz_fields):
        attrs = authz_fields()

    attrs["id"] = str(entity.pk)
    result.add(
        Entity(
            EntityRef(type(entity).__name__, str(entity.pk)),
            attrs=attrs,
        )
    )

    # Transitively include any entities the model declares as related so Cedar
    # can resolve `resource.foo.bar` attribute chains. Models opt in by
    # defining `authz_related_entities()` → iterable of related Django models.
    related_fn = getattr(entity, "authz_related_entities", None)
    if callable(related_fn):
        for related in related_fn() or ():
            result.update(_make_entities(related, principal_attribute_providers))

    return result


def _deep_merge(dst: dict[str, Any], src: Mapping[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, Mapping) and isinstance(dst.get(k), Mapping):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_authz.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
git add src/django_cedar/authz.py tests/test_authz.py
git commit -m "feat: port Authz engine with Entity rename and pluggable context providers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Settings loading, caches, `create_authz`

**Files:**
- Modify: `src/django_cedar/authz.py` (add settings-driven loading)
- Create: `tests/providers.py`
- Create: `tests/test_settings_loading.py`

**Interfaces:**
- Consumes: `Authz`, `_deep_merge` from Task 4
- Produces (all in `django_cedar.authz`):
  - `_resolve_policy_path() -> Path` — resolves `settings.CEDAR_POLICY_PATH` (relative paths against `settings.BASE_DIR`, falling back to `Path.cwd()`); no existence check (also used by Task 7's checks)
  - `get_policies() -> str` (lru_cached; raises `FileNotFoundError` if the file is missing)
  - `import_from_path(path: str)` — imports `"pkg.mod.Attr"`, raises `ImproperlyConfigured` on bad format or missing attribute
  - `get_principal_attr_providers() -> list[Any]`, `get_context_providers() -> list[Any]` (lru_cached; raise `ImproperlyConfigured` if setting is not list/tuple)
  - `create_authz() -> Authz` — wires all of the above
  - Caches auto-clear when any of `CEDAR_POLICY_PATH`, `BASE_DIR`, `CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS`, `CEDAR_CONTEXT_PROVIDERS` changes (Django `setting_changed` signal), so `override_settings` / pytest-django's `settings` fixture work.
  - Test helper classes in `tests/providers.py`: `StaticAttrs` (get_attributes → `{"role": "admin"}`), `SelfSignupContext` (get_context → `{"allow": {"self_signup": True}}`), `Missing` (no methods).

- [ ] **Step 1: Write `tests/providers.py`**

```python
from __future__ import annotations


class StaticAttrs:
    def get_attributes(self, user):
        return {"role": "admin"}


class SelfSignupContext:
    def get_context(self, user, action, resource):
        return {"allow": {"self_signup": True}}


class Missing:
    pass
```

- [ ] **Step 2: Write the failing tests in `tests/test_settings_loading.py`**

```python
from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from django_cedar import authz

PERMIT_ALL = "permit(principal, action, resource);"
DENY_ALL = "forbid(principal, action, resource);"


class TestPolicyPathResolution:
    def test_absolute_path(self, settings, tmp_path):
        policy_file = tmp_path / "policies.cedar"
        policy_file.write_text(PERMIT_ALL)
        settings.CEDAR_POLICY_PATH = str(policy_file)
        assert authz.get_policies() == PERMIT_ALL

    def test_relative_path_resolves_against_base_dir(self, settings, tmp_path):
        (tmp_path / "policies.cedar").write_text(PERMIT_ALL)
        settings.BASE_DIR = tmp_path
        settings.CEDAR_POLICY_PATH = "policies.cedar"
        assert authz.get_policies() == PERMIT_ALL

    def test_missing_file_raises(self, settings, tmp_path):
        settings.CEDAR_POLICY_PATH = str(tmp_path / "nope.cedar")
        with pytest.raises(FileNotFoundError):
            authz.get_policies()

    def test_cache_cleared_when_setting_changes(self, settings, tmp_path):
        first = tmp_path / "first.cedar"
        first.write_text(PERMIT_ALL)
        second = tmp_path / "second.cedar"
        second.write_text(DENY_ALL)

        settings.CEDAR_POLICY_PATH = str(first)
        assert authz.get_policies() == PERMIT_ALL

        settings.CEDAR_POLICY_PATH = str(second)
        assert authz.get_policies() == DENY_ALL

    def test_result_is_cached(self, settings, tmp_path):
        policy_file = tmp_path / "policies.cedar"
        policy_file.write_text(PERMIT_ALL)
        settings.CEDAR_POLICY_PATH = str(policy_file)
        assert authz.get_policies() == PERMIT_ALL

        # Mutating the file without touching settings serves the cached copy.
        policy_file.write_text(DENY_ALL)
        assert authz.get_policies() == PERMIT_ALL


class TestImportFromPath:
    def test_imports_attribute(self):
        cls = authz.import_from_path("tests.providers.StaticAttrs")
        assert cls().get_attributes(None) == {"role": "admin"}

    def test_invalid_format_raises(self):
        with pytest.raises(ImproperlyConfigured):
            authz.import_from_path("noDotsHere")

    def test_missing_attribute_raises(self):
        with pytest.raises(ImproperlyConfigured):
            authz.import_from_path("tests.providers.DoesNotExist")


class TestProviderLoading:
    def test_attr_providers_must_be_list_or_tuple(self, settings):
        settings.CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS = "tests.providers.StaticAttrs"
        with pytest.raises(ImproperlyConfigured):
            authz.get_principal_attr_providers()

    def test_attr_providers_loaded_and_instantiated(self, settings):
        settings.CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS = ["tests.providers.StaticAttrs"]
        providers = authz.get_principal_attr_providers()
        assert len(providers) == 1
        assert providers[0].get_attributes(None) == {"role": "admin"}

    def test_context_providers_default_empty(self):
        assert authz.get_context_providers() == []

    def test_context_providers_loaded(self, settings):
        settings.CEDAR_CONTEXT_PROVIDERS = ["tests.providers.SelfSignupContext"]
        providers = authz.get_context_providers()
        assert len(providers) == 1
        assert providers[0].get_context(None, "X", None) == {
            "allow": {"self_signup": True}
        }

    def test_context_providers_must_be_list_or_tuple(self, settings):
        settings.CEDAR_CONTEXT_PROVIDERS = "tests.providers.SelfSignupContext"
        with pytest.raises(ImproperlyConfigured):
            authz.get_context_providers()

    def test_provider_cache_cleared_when_setting_changes(self, settings):
        settings.CEDAR_CONTEXT_PROVIDERS = []
        assert authz.get_context_providers() == []
        settings.CEDAR_CONTEXT_PROVIDERS = ["tests.providers.SelfSignupContext"]
        assert len(authz.get_context_providers()) == 1


class TestCreateAuthz:
    def test_wires_policies_and_providers(self, settings, tmp_path):
        policy_file = tmp_path / "policies.cedar"
        policy_file.write_text(PERMIT_ALL)
        settings.CEDAR_POLICY_PATH = str(policy_file)
        settings.CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS = ["tests.providers.StaticAttrs"]
        settings.CEDAR_CONTEXT_PROVIDERS = ["tests.providers.SelfSignupContext"]

        instance = authz.create_authz()

        assert instance.policies == PERMIT_ALL
        assert len(instance.principal_attribute_providers) == 1
        assert len(instance.context_providers) == 1

    def test_end_to_end_with_context_provider(self, settings, tmp_path):
        policy_file = tmp_path / "policies.cedar"
        policy_file.write_text(
            "permit(principal, action, resource)"
            " when { context.allow.self_signup };"
        )
        settings.CEDAR_POLICY_PATH = str(policy_file)
        settings.CEDAR_CONTEXT_PROVIDERS = ["tests.providers.SelfSignupContext"]

        from unittest.mock import MagicMock

        user = MagicMock()
        user.pk = 1
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        user.groups.all.return_value = []

        authz.create_authz().authorize(user, "SignUp", None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_settings_loading.py -v`
Expected: FAIL with `AttributeError: module 'django_cedar.authz' has no attribute 'get_policies'` (and similar).

- [ ] **Step 4: Add the settings-loading code to `src/django_cedar/authz.py`**

Add these imports to the existing import block (keep one import per line, alphabetical):

```python
import importlib
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
```

Insert the following after `logger = logging.getLogger(__name__)` and before `class Authz:`:

```python
def _resolve_policy_path() -> Path:
    raw = settings.CEDAR_POLICY_PATH
    p = Path(raw).expanduser()
    if not p.is_absolute():
        base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        p = base / p
    return p.resolve()


def _get_policy_path() -> Path:
    p = _resolve_policy_path()
    if not p.is_file():
        raise FileNotFoundError(f"Policy file not found at {p}")
    return p


@lru_cache(maxsize=1)
def get_policies() -> str:
    return _get_policy_path().read_text()


def import_from_path(path: str):
    try:
        module_path, attr = path.rsplit(".", 1)
    except ValueError as e:
        raise ImproperlyConfigured(
            f"Invalid contributor path '{path}'. Expected 'some.module.ClassName'."
        ) from e

    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as e:
        raise ImproperlyConfigured(
            f"Contributor '{path}' not found (no attribute '{attr}' in "
            f"'{module_path}')."
        ) from e


def _load_providers(setting_name: str) -> list[Any]:
    paths = getattr(settings, setting_name, [])
    if not isinstance(paths, (list, tuple)):
        raise ImproperlyConfigured(f"{setting_name} must be a list/tuple.")
    return [import_from_path(p)() for p in paths]


@lru_cache(maxsize=1)
def get_principal_attr_providers() -> list[Any]:
    return _load_providers("CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS")


@lru_cache(maxsize=1)
def get_context_providers() -> list[Any]:
    return _load_providers("CEDAR_CONTEXT_PROVIDERS")


_SETTING_CACHES = {
    "CEDAR_POLICY_PATH": (get_policies,),
    "BASE_DIR": (get_policies,),
    "CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS": (get_principal_attr_providers,),
    "CEDAR_CONTEXT_PROVIDERS": (get_context_providers,),
}


def _clear_caches_on_setting_change(*, setting, **kwargs) -> None:
    for fn in _SETTING_CACHES.get(setting, ()):
        fn.cache_clear()


setting_changed.connect(
    _clear_caches_on_setting_change,
    dispatch_uid="django_cedar.authz.clear_caches",
)


def create_authz() -> Authz:
    return Authz(
        policies=get_policies(),
        principal_attribute_providers=get_principal_attr_providers(),
        context_providers=get_context_providers(),
    )
```

- [ ] **Step 5: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: PASS (all tests, including Task 4's — nothing regressed).

- [ ] **Step 6: Lint, typecheck, commit**

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
git add src/django_cedar/authz.py tests/providers.py tests/test_settings_loading.py
git commit -m "feat: settings-driven policy/provider loading with override_settings-safe caches

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Views and mixins

**Files:**
- Create: `src/django_cedar/views.py`
- Create: `tests/test_views.py`

**Interfaces:**
- Consumes: `create_authz` from Task 5 (imported as `from django_cedar.authz import create_authz`)
- Produces: `django_cedar.views` with `CedarAuthorizationMixin` (class attr `action_names: dict[str, str]`, methods `authorize_request(request)`, `get_resource(request)`), `ResourceIsCurrentObjectMixin`, `CurrentUserScopedMixin`, `AsyncLoginRequiredMixin`, and `AuthorizedDetailView` / `AuthorizedListView` / `AuthorizedCreateView` / `AuthorizedUpdateView` / `AuthorizedDeleteView` / `AuthorizedTemplateView` / `AuthorizedFormView`.

This is the app-studio `views.py` with exactly one change: `OrganisationScopedMixin` is **not** ported (it depends on app-studio's `user.profile.organisation`). Everything else is verbatim.

- [ ] **Step 1: Write the failing tests in `tests/test_views.py`**

Copy `/Users/acaine/src/hyperscale/app-studio/django_cedar/tests/test_views.py` verbatim — no changes are needed (it only imports `CedarAuthorizationMixin`, `CurrentUserScopedMixin`, and `ResourceIsCurrentObjectMixin`, all of which are ported). Read that file and write its exact content to `tests/test_views.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_views.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'django_cedar.views'`.

- [ ] **Step 3: Write `src/django_cedar/views.py`**

Copy `/Users/acaine/src/hyperscale/app-studio/django_cedar/views.py` verbatim, then delete the entire `OrganisationScopedMixin` class (the block starting `class OrganisationScopedMixin:` through its `get_queryset` method, immediately before `class AuthorizedDetailView`). No other edits — imports, docstrings, and `# type: ignore` comments stay as they are.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_views.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
git add src/django_cedar/views.py tests/test_views.py
git commit -m "feat: port Cedar authorization view mixins and Authorized* views

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: System checks and AppConfig

**Files:**
- Create: `src/django_cedar/checks.py`
- Create: `src/django_cedar/apps.py`
- Create: `tests/test_checks.py`

**Interfaces:**
- Consumes: `_resolve_policy_path`, `import_from_path` from Task 5; `tests/providers.py` classes from Task 5
- Produces: `django_cedar.checks.check_cedar_config(app_configs, **kwargs) -> list[CheckMessage]` registered as a Django system check when `django_cedar` is in `INSTALLED_APPS`. Check IDs:
  - `django_cedar.E001` — `CEDAR_POLICY_PATH` not set (or None/empty)
  - `django_cedar.E002` — policy file does not exist
  - `django_cedar.E003` — policy file fails to parse as Cedar
  - `django_cedar.E004` — a configured provider dotted path fails to import
  - `django_cedar.E005` — a configured provider lacks its required method (`get_attributes` for attribute providers, `get_context` for context providers)

- [ ] **Step 1: Write the failing tests in `tests/test_checks.py`**

```python
from __future__ import annotations

from django.core.checks.registry import registry

from django_cedar.checks import check_cedar_config


def _error_ids(errors):
    return [e.id for e in errors]


class TestPolicyChecks:
    def test_valid_config_produces_no_errors(self):
        # tests/settings.py points CEDAR_POLICY_PATH at tests/policies.cedar
        assert check_cedar_config(None) == []

    def test_unset_policy_path(self, settings):
        settings.CEDAR_POLICY_PATH = None
        assert _error_ids(check_cedar_config(None)) == ["django_cedar.E001"]

    def test_missing_policy_file(self, settings, tmp_path):
        settings.CEDAR_POLICY_PATH = str(tmp_path / "nope.cedar")
        assert _error_ids(check_cedar_config(None)) == ["django_cedar.E002"]

    def test_unparseable_policy_file(self, settings, tmp_path):
        bad = tmp_path / "bad.cedar"
        bad.write_text("this is not a cedar policy")
        settings.CEDAR_POLICY_PATH = str(bad)
        assert _error_ids(check_cedar_config(None)) == ["django_cedar.E003"]


class TestProviderChecks:
    def test_unimportable_provider_module(self, settings):
        settings.CEDAR_CONTEXT_PROVIDERS = ["not_a_real.module.Thing"]
        assert "django_cedar.E004" in _error_ids(check_cedar_config(None))

    def test_provider_missing_attribute(self, settings):
        settings.CEDAR_CONTEXT_PROVIDERS = ["tests.providers.DoesNotExist"]
        assert "django_cedar.E004" in _error_ids(check_cedar_config(None))

    def test_context_provider_missing_get_context(self, settings):
        settings.CEDAR_CONTEXT_PROVIDERS = ["tests.providers.Missing"]
        assert "django_cedar.E005" in _error_ids(check_cedar_config(None))

    def test_attr_provider_missing_get_attributes(self, settings):
        # SelfSignupContext has get_context but not get_attributes, so it is
        # invalid as a principal attribute provider.
        settings.CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS = [
            "tests.providers.SelfSignupContext"
        ]
        assert "django_cedar.E005" in _error_ids(check_cedar_config(None))

    def test_valid_providers_pass(self, settings):
        settings.CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS = ["tests.providers.StaticAttrs"]
        settings.CEDAR_CONTEXT_PROVIDERS = ["tests.providers.SelfSignupContext"]
        assert check_cedar_config(None) == []


class TestCheckRegistration:
    def test_check_is_registered(self):
        # apps.py ready() imports checks, which registers via @register().
        assert check_cedar_config in registry.registered_checks
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_checks.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'django_cedar.checks'`.

- [ ] **Step 3: Write `src/django_cedar/checks.py`**

```python
from __future__ import annotations

from typing import Any

from cedarpy import format_policies
from django.conf import settings
from django.core.checks import CheckMessage
from django.core.checks import Error
from django.core.checks import register
from django.core.exceptions import ImproperlyConfigured

from django_cedar.authz import _resolve_policy_path
from django_cedar.authz import import_from_path

_PROVIDER_SETTINGS = (
    ("CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS", "get_attributes"),
    ("CEDAR_CONTEXT_PROVIDERS", "get_context"),
)


@register()
def check_cedar_config(
    app_configs: Any, **kwargs: Any
) -> list[CheckMessage]:
    errors: list[CheckMessage] = []
    errors.extend(_check_policy_file())
    errors.extend(_check_providers())
    return errors


def _check_policy_file() -> list[CheckMessage]:
    if not getattr(settings, "CEDAR_POLICY_PATH", None):
        return [
            Error(
                "The CEDAR_POLICY_PATH setting is not set.",
                hint="Set CEDAR_POLICY_PATH to the path of your Cedar policy "
                "file (relative paths resolve against BASE_DIR).",
                id="django_cedar.E001",
            )
        ]
    path = _resolve_policy_path()
    if not path.is_file():
        return [
            Error(
                f"Cedar policy file not found at {path}.",
                hint="Check the CEDAR_POLICY_PATH setting.",
                id="django_cedar.E002",
            )
        ]
    try:
        format_policies(path.read_text())
    except Exception as e:  # cedarpy raises on any parse failure
        return [
            Error(
                f"Cedar policy file at {path} failed to parse: {e}",
                id="django_cedar.E003",
            )
        ]
    return []


def _check_providers() -> list[CheckMessage]:
    errors: list[CheckMessage] = []
    for setting_name, required_method in _PROVIDER_SETTINGS:
        for dotted_path in getattr(settings, setting_name, []):
            try:
                provider_cls = import_from_path(dotted_path)
            except (ImportError, ImproperlyConfigured) as e:
                errors.append(
                    Error(
                        f"Could not import '{dotted_path}' from {setting_name}: {e}",
                        id="django_cedar.E004",
                    )
                )
                continue
            if not callable(getattr(provider_cls, required_method, None)):
                errors.append(
                    Error(
                        f"'{dotted_path}' in {setting_name} does not define a "
                        f"callable '{required_method}' method.",
                        id="django_cedar.E005",
                    )
                )
    return errors
```

- [ ] **Step 4: Write `src/django_cedar/apps.py`**

```python
from django.apps import AppConfig


class DjangoCedarConfig(AppConfig):
    name = "django_cedar"
    verbose_name = "Django Cedar"

    def ready(self) -> None:
        # Importing the module registers the system checks.
        from django_cedar import checks  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_checks.py -v`
Expected: PASS. If `test_unparseable_policy_file` fails because `format_policies` does not raise, check what `cedarpy.format_policies("this is not a cedar policy")` actually does in `uv run python` and adapt the parse check to use `cedarpy.policies_to_json_str` instead (it must raise on invalid input) — keep the same check ID and test.

- [ ] **Step 6: Verify the full suite and the check works end-to-end**

Run:
```bash
uv run pytest -v
uv run python -c "
import django
from django.conf import settings as s
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.settings'
django.setup()
from django.core.checks import run_checks
print('check errors:', run_checks())
"
```
Expected: pytest passes; the script prints `check errors: []`.

- [ ] **Step 7: Lint, typecheck, commit**

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
git add src/django_cedar/checks.py src/django_cedar/apps.py tests/test_checks.py
git commit -m "feat: add optional AppConfig with Cedar configuration system checks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Public API (`__init__.py` lazy exports)

**Files:**
- Modify: `src/django_cedar/__init__.py`
- Create: `tests/test_public_api.py`
- Modify: `tests/test_packaging.py` (add laziness assertion)

**Interfaces:**
- Consumes: `Authz`, `Entity`, `EntityRef`, `create_authz` from `django_cedar.authz`
- Produces: `from django_cedar import Authz, Entity, EntityRef, create_authz` works — lazily via PEP 562, so `import django_cedar` never imports Django models (required: Django imports this package during app loading, before models are ready).

- [ ] **Step 1: Write the failing tests**

`tests/test_public_api.py`:

```python
from __future__ import annotations

import pytest


def test_public_exports_resolve():
    import django_cedar

    from django_cedar.authz import Authz
    from django_cedar.authz import create_authz
    from django_cedar.authz import Entity
    from django_cedar.authz import EntityRef

    assert django_cedar.Authz is Authz
    assert django_cedar.Entity is Entity
    assert django_cedar.EntityRef is EntityRef
    assert django_cedar.create_authz is create_authz


def test_all_matches_exports():
    import django_cedar

    assert set(django_cedar.__all__) == {"Authz", "Entity", "EntityRef", "create_authz"}


def test_unknown_attribute_raises():
    import django_cedar

    with pytest.raises(AttributeError):
        django_cedar.does_not_exist
```

Append to `tests/test_packaging.py`:

```python
def test_import_is_lazy():
    """Importing the package must not pull in authz (which imports Django models)."""
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    code = (
        "import sys; import django_cedar; "
        "assert 'django_cedar.authz' not in sys.modules, 'authz imported eagerly'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_public_api.py tests/test_packaging.py -v`
Expected: `test_public_exports_resolve`, `test_all_matches_exports`, `test_unknown_attribute_raises` FAIL with `AttributeError` (empty `__init__.py`); the packaging tests still pass.

- [ ] **Step 3: Write `src/django_cedar/__init__.py`**

```python
"""Cedar policy-based authorization for Django."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["Authz", "Entity", "EntityRef", "create_authz"]

# PEP 562 lazy exports: Django imports this package during app loading, when
# models are not yet ready — so django_cedar.authz (which imports auth models)
# must not be imported until an attribute is actually accessed.


def __getattr__(name: str) -> Any:
    if name in __all__:
        return getattr(importlib.import_module("django_cedar.authz"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: PASS (all tests).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
git add src/django_cedar/__init__.py tests/test_public_api.py tests/test_packaging.py
git commit -m "feat: lazy public API exports

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Documentation (README, CHANGELOG, SECURITY, CONTRIBUTING)

**Files:**
- Modify: `README.md` (replace placeholder)
- Create: `CHANGELOG.md`
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: the public API from Tasks 4–8 (examples must match it exactly)
- Produces: user-facing docs; README is the PyPI long description.

- [ ] **Step 1: Write `README.md`**

````markdown
# django-cedar

[Cedar](https://www.cedarpolicy.com/) policy-based authorization for Django.

Cedar is an open-source policy language for expressive, analyzable
permissions. django-cedar lets you express *who can do what* in Cedar policy
files instead of scattering permission logic through your views, and enforces
those policies with class-based-view mixins.

## Requirements

- Python 3.12+
- Django 5.2+

## Installation

```bash
pip install django-cedar
```

Add the app (optional, but recommended — it enables startup-time
configuration checks via Django's system check framework):

```python
INSTALLED_APPS = [
    # ...
    "django_cedar",
]
```

## Quickstart

**1. Write a policy file** (`policies.cedar` next to `manage.py`):

```cedar
// Staff can do anything
permit(principal, action, resource)
when { principal.is_staff };

// Anyone signed in can view widgets
permit(principal is User, action == Action::"ViewWidget", resource);
```

**2. Point Django at it:**

```python
CEDAR_POLICY_PATH = "policies.cedar"  # relative paths resolve against BASE_DIR
```

**3. Enforce it in your views:**

```python
from django_cedar.views import AuthorizedDetailView

from .models import Widget


class WidgetDetailView(AuthorizedDetailView):
    model = Widget
    action_names = {"GET": "ViewWidget"}
```

Every request is authorized in `dispatch()`. The Cedar request is built as:

- **principal** — `User::"<pk>"` for authenticated users, `Anonymous::"guest"`
  otherwise. User entities carry `id`, `is_staff` and `is_superuser`
  attributes, and the user's Django groups become parent entities
  (`Group::"<name>"`), so `principal in Group::"editors"` works out of the box.
- **action** — `Action::"<name>"` from the view's `action_names` mapping
  (HTTP method → action name).
- **resource** — the object returned by the view's `get_resource()` hook, as
  `<ModelClass>::"<pk>"`; `System::"global"` when there is no resource.

Denied requests raise `django.core.exceptions.PermissionDenied` (HTTP 403).

## Views and mixins

| Class | Resource used for the check |
|---|---|
| `AuthorizedDetailView` / `AuthorizedUpdateView` / `AuthorizedDeleteView` | `self.get_object()` |
| `AuthorizedListView` / `AuthorizedCreateView` / `AuthorizedTemplateView` / `AuthorizedFormView` | `System::"global"` (override `get_resource()`) |

Compose the behavior yourself with `CedarAuthorizationMixin` plus:

- `ResourceIsCurrentObjectMixin` — authorize against `self.get_object()`.
- `CurrentUserScopedMixin` — authorize against the current user and filter
  the queryset to `user=<request.user>`.
- `AsyncLoginRequiredMixin` — a `LoginRequiredMixin` that works on async
  views. `CedarAuthorizationMixin` itself supports async views too.

Custom scoping is one method:

```python
class ProjectScopedView(CedarAuthorizationMixin, ListView):
    action_names = {"GET": "ListTasks"}

    def get_resource(self, request):
        return Project.objects.get(pk=self.kwargs["project_pk"])
```

## Exposing model attributes to policies

Models opt in to exposing attributes with `authz_fields()`, and pull related
entities into the request with `authz_related_entities()`:

```python
class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    status = models.CharField(max_length=20)

    def authz_fields(self):
        return {"status": self.status, "project": str(self.project_id)}

    def authz_related_entities(self):
        return [self.project]
```

```cedar
permit(principal, action == Action::"CloseTask", resource is Task)
when { resource.status == "open" };
```

## Settings

| Setting | Required | Description |
|---|---|---|
| `CEDAR_POLICY_PATH` | yes | Path to the Cedar policy file. Relative paths resolve against `BASE_DIR`. |
| `CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS` | no | List of dotted paths to classes with `get_attributes(user) -> dict` (extra principal attributes) and optionally `get_entities(user) -> iterable[Entity]` (extra entities). |
| `CEDAR_CONTEXT_PROVIDERS` | no | List of dotted paths to classes with `get_context(user, action, resource) -> dict`. Results are deep-merged into the Cedar request context in list order; a per-call `context=` argument merges last and wins. |

Example context provider:

```python
class FeatureFlagContext:
    def get_context(self, user, action, resource):
        return {"allow": {"self_signup": settings.ALLOW_SELF_SIGNUP}}
```

## Using the engine directly

```python
from django_cedar import create_authz

authz = create_authz()  # loads policies + providers from settings (cached)
authz.authorize(request.user, "ExportReport", report)  # raises PermissionDenied on deny
```

## System checks

With `django_cedar` in `INSTALLED_APPS`, `manage.py check` (and every server
start) verifies that `CEDAR_POLICY_PATH` is set and the file exists
(`django_cedar.E001`/`E002`), that it parses as Cedar (`E003`), and that all
configured providers import and have the right methods (`E004`/`E005`).

## License

Apache-2.0
````

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - TBD

### Added

- Initial release, extracted from an internal Hyperscale project.
- `Authz` engine wrapping `cedarpy.is_authorized`, with settings-driven
  `create_authz()` factory.
- `CEDAR_POLICY_PATH`, `CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS` and
  `CEDAR_CONTEXT_PROVIDERS` settings.
- Class-based-view enforcement: `CedarAuthorizationMixin`,
  `ResourceIsCurrentObjectMixin`, `CurrentUserScopedMixin`,
  `AsyncLoginRequiredMixin`, and `Authorized*` view classes.
- `authz_fields()` / `authz_related_entities()` model protocols.
- Optional Django app with system checks for Cedar configuration.
```

(The `TBD` date is filled in by Task 13 when the release is actually cut.)

- [ ] **Step 3: Write `SECURITY.md`**

```markdown
# Security Policy

## Supported Versions

The latest minor release receives security fixes.

## Reporting a Vulnerability

Please report vulnerabilities privately via GitHub's
[private vulnerability reporting](https://github.com/hyperscale-consulting/django-cedar/security/advisories/new)
— do not open a public issue for security problems.

You should receive an initial response within 5 working days.
```

- [ ] **Step 4: Write `CONTRIBUTING.md`**

````markdown
# Contributing

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
git clone https://github.com/hyperscale-consulting/django-cedar.git
cd django-cedar
uv sync
uvx pre-commit install
```

## Running checks

```bash
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format --check .   # formatting
uv run pyright                 # types
```

Test against a specific Django line:

```bash
uv run --with "django~=5.2.0" pytest
uv run --with "django~=6.0.0" pytest
```

CI runs the full matrix (Python 3.12–3.14 × Django 5.2/6.0) on every PR.

## Pull requests

- Add tests for behavior changes.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Keep the public API documented in `README.md`.
````

- [ ] **Step 5: Verify docs don't break tooling and examples match the API**

Run:
```bash
uv run pytest -v
uvx pre-commit run --all-files
DJANGO_SETTINGS_MODULE=tests.settings uv run python -c "from django_cedar.views import AuthorizedDetailView, CedarAuthorizationMixin, CurrentUserScopedMixin, ResourceIsCurrentObjectMixin, AsyncLoginRequiredMixin; from django_cedar import Authz, Entity, EntityRef, create_authz; print('README API surface ok')"
```
Expected: all pass; the import check prints `README API surface ok`.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md
git commit -m "docs: README, changelog, security policy and contributing guide

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: CI workflow, Dependabot

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/dependabot.yml`

**Interfaces:**
- Consumes: everything — CI runs the whole toolchain
- Produces: `ci.yml` jobs `lint`, `test` (matrix), `build`, `pip-audit`, `zizmor`; Dependabot config. Task 12 requires these to go green on GitHub.

- [ ] **Step 1: Resolve action SHAs**

For each action, resolve the tag to a full commit SHA (the `commits/<ref>` endpoint dereferences annotated tags):

```bash
gh api repos/actions/checkout/commits/v5 --jq .sha
gh api repos/astral-sh/setup-uv/commits/v7 --jq .sha
```

If a tag doesn't exist (404), list available tags with `gh api repos/<owner>/<repo>/tags --jq '.[].name' | head` and use the newest major. Record each SHA and use it below with a `# vN` comment.

- [ ] **Step 2: Write `.github/workflows/ci.yml`** (replace `<CHECKOUT_SHA>` / `<SETUP_UV_SHA>` with the SHAs from Step 1)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions: {}

jobs:
  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<CHECKOUT_SHA> # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP_UV_SHA> # v7
      - run: uv sync --locked
      - run: uv run ruff check --no-fix .
      - run: uv run ruff format --check .
      - run: uv run pyright

  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13", "3.14"]
        django-version: ["5.2", "6.0"]
    steps:
      - uses: actions/checkout@<CHECKOUT_SHA> # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP_UV_SHA> # v7
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --locked
      - run: uv pip install "django~=${{ matrix.django-version }}.0"
      - run: uv run pytest --cov=django_cedar --cov-report=term-missing

  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<CHECKOUT_SHA> # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP_UV_SHA> # v7
      - run: uv build
      - run: uvx twine check dist/*

  pip-audit:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<CHECKOUT_SHA> # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP_UV_SHA> # v7
      - run: uv export --no-emit-project --format requirements-txt -o requirements.txt
      - run: uvx pip-audit --disable-pip -r requirements.txt

  zizmor:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<CHECKOUT_SHA> # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP_UV_SHA> # v7
      - run: uvx zizmor .github/workflows/
```

- [ ] **Step 3: Write `.github/dependabot.yml`**

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

- [ ] **Step 4: Verify the workflow locally as far as possible**

Run:
```bash
uvx zizmor .github/workflows/
uv export --no-emit-project --format requirements-txt -o /tmp/reqs.txt && uvx pip-audit --disable-pip -r /tmp/reqs.txt
uv run pytest --cov=django_cedar --cov-report=term-missing
```
Expected: zizmor reports no findings (fix any it raises — e.g. missing `persist-credentials: false` — before committing); pip-audit finds no known vulnerabilities; pytest passes with coverage output.

- [ ] **Step 5: Commit**

```bash
git add .github
git commit -m "ci: lint, test matrix, build, pip-audit and zizmor workflows; dependabot

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Publish workflow (PyPI Trusted Publishing)

**Files:**
- Create: `.github/workflows/publish.yml`

**Interfaces:**
- Consumes: action SHAs approach from Task 10
- Produces: a release-triggered publish pipeline. Requires (Task 13): PyPI trusted publisher configured for workflow `publish.yml`, environment `pypi`.

- [ ] **Step 1: Resolve additional action SHAs**

```bash
gh api repos/actions/upload-artifact/commits/v4 --jq .sha
gh api repos/actions/download-artifact/commits/v4 --jq .sha
gh api repos/pypa/gh-action-pypi-publish/commits/release/v1 --jq .sha
```

(Same fallback as Task 10 Step 1 if a ref is missing.)

- [ ] **Step 2: Write `.github/workflows/publish.yml`** (substitute all SHAs)

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

permissions: {}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<CHECKOUT_SHA> # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP_UV_SHA> # v7
      - run: uv build
      - run: uvx twine check dist/*
      - uses: actions/upload-artifact@<UPLOAD_ARTIFACT_SHA> # v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@<DOWNLOAD_ARTIFACT_SHA> # v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@<PYPI_PUBLISH_SHA> # release/v1
```

Notes: no PyPI token is configured anywhere — authentication is OIDC via the trusted publisher; the action also generates PEP 740 attestations by default.

- [ ] **Step 3: Lint the workflow**

Run: `uvx zizmor .github/workflows/publish.yml`
Expected: no findings.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "ci: publish to PyPI via trusted publishing on GitHub release

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: GitHub repo creation, push, security configuration

**Files:** none (GitHub-side configuration)

**Interfaces:**
- Consumes: all committed work; `gh` CLI authenticated as `andycaine` with access to `hyperscale-consulting`
- Produces: public repo `hyperscale-consulting/django-cedar` with CI green, CodeQL default setup, Dependabot alerts + security fixes, private vulnerability reporting, and a `pypi` environment.

- [ ] **Step 1: Create the repo and push**

```bash
gh repo create hyperscale-consulting/django-cedar --public --source . --push \
  --description "Cedar policy-based authorization for Django" \
  --homepage "https://pypi.org/project/django-cedar/"
```

Expected: repo created, `main` pushed, `origin` remote configured.

- [ ] **Step 2: Enable security features**

```bash
gh api -X PUT repos/hyperscale-consulting/django-cedar/vulnerability-alerts
gh api -X PUT repos/hyperscale-consulting/django-cedar/automated-security-fixes
gh api -X PUT repos/hyperscale-consulting/django-cedar/private-vulnerability-reporting
gh api -X PATCH repos/hyperscale-consulting/django-cedar/code-scanning/default-setup -f state=configured
```

Expected: each returns 204 (the code-scanning call returns 200 with a run link). If the CodeQL call fails with "no supported languages", wait a minute after push and retry — language detection needs the initial push indexed.

- [ ] **Step 3: Verify secret scanning + push protection are on**

Run: `gh api repos/hyperscale-consulting/django-cedar --jq .security_and_analysis`
Expected: `secret_scanning` and `secret_scanning_push_protection` show `"status": "enabled"` (default for public repos). If not, enable via:
`gh api -X PATCH repos/hyperscale-consulting/django-cedar -f 'security_and_analysis[secret_scanning][status]=enabled' -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'`

- [ ] **Step 4: Create the `pypi` environment**

```bash
gh api -X PUT repos/hyperscale-consulting/django-cedar/environments/pypi
```

Expected: 200 with the environment JSON.

- [ ] **Step 5: Watch CI go green**

```bash
gh run list --repo hyperscale-consulting/django-cedar
gh run watch --repo hyperscale-consulting/django-cedar --exit-status
```

Expected: the CI workflow run for the push to `main` completes with all jobs passing. If any job fails, fix it (this is the first run on GitHub's runners — likely causes: a missing SHA pin typo, or matrix cell dependency resolution) and push the fix before proceeding.

- [ ] **Step 6: Commit nothing — confirm clean tree**

Run: `git status --short`
Expected: empty output.

---

### Task 13: Release 0.1.0 (blocks on user action)

**Files:**
- Modify: `CHANGELOG.md` (set the 0.1.0 date)

**Interfaces:**
- Consumes: green CI from Task 12; publish workflow from Task 11
- Produces: `django-cedar 0.1.0` on PyPI.

- [ ] **Step 1: STOP — ask the user to configure the PyPI trusted publisher**

This step requires the user. Tell them exactly:

> Before I can cut the release, please add a **pending trusted publisher** on PyPI: go to https://pypi.org/manage/account/publishing/ → "Add a new pending publisher" (GitHub tab) and enter:
> - PyPI project name: `django-cedar`
> - Owner: `hyperscale-consulting`
> - Repository name: `django-cedar`
> - Workflow name: `publish.yml`
> - Environment name: `pypi`
>
> Tell me when that's done.

Do not proceed until the user confirms.

- [ ] **Step 2: Set the release date in `CHANGELOG.md`**

Change the line `## [0.1.0] - TBD` to `## [0.1.0] - <today's date in YYYY-MM-DD>` and commit:

```bash
git add CHANGELOG.md
git commit -m "chore: date 0.1.0 release

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

- [ ] **Step 3: Cut the release**

```bash
gh release create v0.1.0 --repo hyperscale-consulting/django-cedar \
  --title "v0.1.0" \
  --notes "Initial release. Cedar policy-based authorization for Django: Authz engine, CBV mixins, pluggable principal-attribute and context providers, and configuration system checks. See CHANGELOG.md."
```

- [ ] **Step 4: Watch the publish workflow**

```bash
gh run watch --repo hyperscale-consulting/django-cedar --exit-status
```

Expected: `Publish to PyPI` workflow succeeds (build → publish via OIDC).

- [ ] **Step 5: Verify the package is live and installable**

```bash
curl -s https://pypi.org/pypi/django-cedar/json | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version'])"
uv run --no-project --with django-cedar python -c "import django_cedar; print('installed ok')"
```

Expected: prints `0.1.0` then `installed ok`. (PyPI can take a minute to index — retry once if the first check 404s.)

---

## Verification (whole plan)

- `uv run pytest` — full suite green.
- `uv run ruff check . && uv run ruff format --check . && uv run pyright` — clean.
- `uvx pre-commit run --all-files` — clean.
- `uv build && uvx twine check dist/*` — passes.
- GitHub: CI green on `main`; CodeQL, secret scanning + push protection, Dependabot, private vulnerability reporting all enabled.
- PyPI: `django-cedar 0.1.0` published via trusted publishing.
