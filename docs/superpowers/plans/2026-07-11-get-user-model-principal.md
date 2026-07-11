# get_user_model() Principals (0.2.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `AbstractUser`/`User` principal assumption with `get_user_model()`-based construction so any Django user model works, then release 0.2.0.

**Architecture:** The Cedar principal type derives from `get_user_model().__name__` everywhere (request string and entity store); user attributes (`is_staff`/`is_superuser`) and `Group` parents are capability-detected via `hasattr` instead of assumed. A user-model instance passed as a *resource* is detected with `isinstance(obj, get_user_model())` (which sees through `SimpleLazyObject`) and named consistently with the principal.

**Tech Stack:** Existing repo tooling — uv, pytest + pytest-django, ruff, pyright, pre-commit, GitHub Actions (CI + trusted-publishing release).

**Spec:** `docs/superpowers/specs/2026-07-11-get-user-model-principal-design.md`

## Global Constraints

- Behavior for projects on Django's default `User` model must be byte-identical to 0.1.x (class name is `User`).
- Anonymous principal unchanged: `Anonymous::"guest"`. Group vocabulary unchanged: `Group::"<name>"`.
- No caching of `get_user_model()` — call it at authorization time so `AUTH_USER_MODEL` overrides in tests resolve correctly.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright` (0 errors) before every commit; pyright fixes use targeted `Any`/`cast` at dynamic Django boundaries — never django-stubs, never `# type: ignore`.
- One `from x import y` per line (ruff isort, force-single-line).
- No new dependencies; runtime deps stay exactly `django>=5.2`, `cedarpy>=4.8.1`.
- Version: 0.2.0. `views.py` must not change.
- End every commit message with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Work on `main` in /Users/acaine/src/django-cedar; pre-commit hooks run on commit (if they auto-fix, `git add` and retry).

---

### Task 1: Test-harness user models

**Files:**
- Create: `tests/models.py`
- Modify: `tests/settings.py` (add `"tests"` to INSTALLED_APPS)

**Interfaces:**
- Consumes: existing test harness (`tests/settings.py`, pytest-django).
- Produces: importable concrete models `tests.models.Member` (full-featured `AbstractUser` subclass) and `tests.models.Device` (bare `AbstractBaseUser`), swappable in tests via `settings.AUTH_USER_MODEL = "tests.Member"` / `"tests.Device"`. Task 2's tests import both.

- [ ] **Step 1: Write `tests/models.py`**

`Member` must override the `groups`/`user_permissions` M2M fields with custom `related_name`s — the default `auth.User` model stays installed alongside it, and two concrete models inheriting `PermissionsMixin` defaults would collide on reverse accessors (system check `fields.E304`, which would abort test-database creation).

```python
from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AbstractUser
from django.db import models


class Member(AbstractUser):
    """Custom full-featured user model for AUTH_USER_MODEL swap tests.

    The related_name overrides avoid reverse-accessor clashes with the
    concurrently installed default ``auth.User`` model.
    """

    groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="member_set",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        blank=True,
        related_name="member_set",
    )


class Device(AbstractBaseUser):
    """Bare user model: no is_staff/is_superuser, no groups."""

    identifier = models.CharField(max_length=64, unique=True)

    USERNAME_FIELD = "identifier"
```

- [ ] **Step 2: Register the tests app**

In `tests/settings.py`, change:

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django_cedar",
]
```

to:

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django_cedar",
    "tests",
]
```

- [ ] **Step 3: Verify nothing regressed and no model-check errors**

Run:
```bash
uv run pytest -q
DJANGO_SETTINGS_MODULE=tests.settings uv run python -c "
import django
django.setup()
from django.core.checks import run_checks
errors = run_checks()
print('check errors:', errors)
assert not errors
"
```
Expected: full suite passes (87 tests); `check errors: []`. If `fields.E304` errors appear, the `related_name` overrides in Step 1 are wrong — fix them, do not silence checks.

- [ ] **Step 4: Lint, typecheck, commit**

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
git add tests/models.py tests/settings.py
git commit -m "test: add swappable custom user models to the harness

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: get_user_model()-based principal construction

**Files:**
- Modify: `src/django_cedar/authz.py`
- Create: `tests/test_user_models.py`

**Interfaces:**
- Consumes: `tests.models.Member` / `tests.models.Device` from Task 1; existing `_cedar_uid`, `Entity`, `EntityRef`, `Authz`, `_make_principal_entities`.
- Produces (module-private, used within `authz.py` and by tests):
  - `_principal_type() -> str` — `get_user_model().__name__`
  - `_entity_type(obj: Any) -> str` — principal type if `isinstance(obj, get_user_model())`, else `type(obj).__name__`
  - `_make_user_entities` / `_make_principal_entities` / `Authz.authorize` re-typed to `AbstractBaseUser` and capability-detecting; external behavior for default-`User` projects unchanged.

- [ ] **Step 1: Write the failing tests in `tests/test_user_models.py`**

Notes on the test design:
- `settings.AUTH_USER_MODEL = "tests.Member"` uses the pytest-django `settings` fixture (fires `setting_changed`; `get_user_model()` re-resolves per call, so no cache wiring is needed).
- Tests touching `Member` principal entities need `pytest.mark.django_db`: `_make_user_entities` evaluates `groups.all()`, which queries the (empty) table even for unsaved instances with an explicit `pk`. `Device` has no `groups`, so its tests need no DB.
- The default-path regression (principal stays `User::"<pk>"` with stock settings) is already pinned by `tests/test_authz.py::TestAuthzAuthorize::test_authenticated_user_uses_user_principal` — no duplicate needed.

```python
from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied

from django_cedar.authz import _make_principal_entities
from django_cedar.authz import Authz
from django_cedar.authz import EntityRef
from tests.models import Device
from tests.models import Member


@pytest.mark.django_db
class TestCustomUserPrincipal:
    def test_principal_type_is_model_class_name(self, settings):
        settings.AUTH_USER_MODEL = "tests.Member"
        policy = 'permit(principal == Member::"7", action, resource);'
        authz = Authz(policies=policy)
        authz.authorize(Member(pk=7), "DoSomething", None)

    def test_hardcoded_user_type_no_longer_matches(self, settings):
        settings.AUTH_USER_MODEL = "tests.Member"
        policy = 'permit(principal == User::"7", action, resource);'
        authz = Authz(policies=policy)
        with pytest.raises(PermissionDenied):
            authz.authorize(Member(pk=7), "DoSomething", None)

    def test_full_featured_model_keeps_flag_attrs(self, settings):
        settings.AUTH_USER_MODEL = "tests.Member"
        member = Member(pk=3, is_staff=True, is_superuser=False)
        entities = _make_principal_entities(member, principal_attribute_providers=[])
        principal = next(e for e in entities if e.ref.type == "Member")
        assert principal.attrs["id"] == "3"
        assert principal.attrs["is_staff"] is True
        assert principal.attrs["is_superuser"] is False

    def test_user_as_resource_types_match(self, settings):
        settings.AUTH_USER_MODEL = "tests.Member"
        policy = """
        permit(principal, action, resource is Member)
        when { resource.id == "9" };
        """
        authz = Authz(policies=policy)
        member = Member(pk=9)
        authz.authorize(member, "ViewProfile", member)


@pytest.mark.django_db
class TestCustomUserGroups:
    def test_group_parents_and_group_entities(self, settings):
        from django.contrib.auth.models import Group

        settings.AUTH_USER_MODEL = "tests.Member"
        member = Member.objects.create(username="alice")
        group = Group.objects.create(name="editors")
        member.groups.add(group)

        entities = _make_principal_entities(member, principal_attribute_providers=[])
        principal = next(e for e in entities if e.ref.type == "Member")
        assert EntityRef("Group", "editors") in principal.parents
        group_entity = next(e for e in entities if e.ref.type == "Group")
        assert group_entity.attrs["id"] == str(group.pk)


class TestBareUserModel:
    def test_entity_has_only_id_and_no_parents(self, settings):
        settings.AUTH_USER_MODEL = "tests.Device"
        device = Device(pk=11)
        entities = _make_principal_entities(device, principal_attribute_providers=[])
        assert len(entities) == 1
        entity = next(iter(entities))
        assert entity.ref.type == "Device"
        assert entity.attrs == {"id": "11"}
        assert entity.parents == set()

    def test_authorize_works_without_flag_attrs(self, settings):
        settings.AUTH_USER_MODEL = "tests.Device"
        policy = "permit(principal is Device, action, resource);"
        authz = Authz(policies=policy)
        authz.authorize(Device(pk=11), "Ping", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_user_models.py -v`
Expected: FAIL — the two policy tests in `TestCustomUserPrincipal` and both `TestBareUserModel` tests fail (principal is still built as `User::"..."`; `Device` lacks `is_staff` so `_make_user_entities` raises `AttributeError`). `test_hardcoded_user_type_no_longer_matches` will PASS-for-the-wrong-reason only if others fail — confirm the overall run is red before proceeding.

- [ ] **Step 3: Modify `src/django_cedar/authz.py`**

3a. Imports — remove:
```python
from django.contrib.auth.models import AbstractUser
```
add (one per line; ruff will order):
```python
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
```

3b. Add two helpers immediately after `_cedar_uid`:
```python
def _principal_type() -> str:
    return get_user_model().__name__


def _entity_type(obj: Any) -> str:
    if isinstance(obj, get_user_model()):
        return _principal_type()
    return type(obj).__name__
```

3c. In `Authz.authorize`, change the signature's user hint and the two UID constructions:
- `user: AbstractUser | None` → `user: AbstractBaseUser | None`
- `_cedar_uid(type(resource).__name__, str(resource.pk))` → `_cedar_uid(_entity_type(resource), str(resource.pk))`
- `principal = _cedar_uid("User", str(user.pk))` → `principal = _cedar_uid(_principal_type(), str(user.pk))`

3d. Replace `_make_user_entities` in full:
```python
def _make_user_entities(
    user: AbstractBaseUser, principal_attribute_providers: list[Any]
) -> set[Entity]:
    user_groups: Any = getattr(user, "groups", None)
    groups = list(user_groups.all()) if user_groups is not None else []
    result = set()
    attrs: dict[str, Any] = {"id": str(user.pk)}
    for flag in ("is_staff", "is_superuser"):
        if hasattr(user, flag):
            attrs[flag] = getattr(user, flag)
    for provider in principal_attribute_providers:
        attrs.update(provider.get_attributes(user))
        if hasattr(provider, "get_entities"):
            result.update(provider.get_entities(user))

    result.add(
        Entity(
            EntityRef(_principal_type(), str(user.pk)),
            attrs=attrs,
            parents={EntityRef("Group", group.name) for group in groups},
        )
    )
    for group in groups:
        result.add(
            Entity(
                EntityRef("Group", group.name),
                attrs={"id": str(group.pk)},
            )
        )
    return result
```

3e. In `_make_principal_entities`, change the hint `user: AbstractUser | None` → `user: AbstractBaseUser | None`.

3f. In `_make_entities`, change:
```python
    if isinstance(entity, AbstractUser):
```
to:
```python
    if isinstance(entity, get_user_model()):
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run:
```bash
uv run pytest tests/test_user_models.py -v
uv run pytest -q
```
Expected: new file all green; full suite green (94 tests: 87 + 7 new) — in particular the existing mock-based tests in `tests/test_authz.py` must be untouched and passing (mocks are not instances of the active user model, so they exercise the default `User` naming and the plain-resource branch exactly as before).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
git add src/django_cedar/authz.py tests/test_user_models.py
git commit -m "feat: derive Cedar principal from get_user_model()

The principal entity type now follows the active user model's class
name; is_staff/is_superuser attributes and Group parents are included
only when the model provides them, so any user model works — including
bare AbstractBaseUser. Fixes principal/resource type mismatch for
custom user models.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Docs and version bump

**Files:**
- Modify: `README.md` (Requirements section)
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml` (version)

**Interfaces:**
- Consumes: behavior implemented in Task 2 (docs must describe it exactly).
- Produces: version `0.2.0` in `pyproject.toml` (Task 4 releases it); `uv.lock` refreshed.

- [ ] **Step 1: Update the README Requirements section**

Replace:
```markdown
Your user model must subclass
`django.contrib.auth.models.AbstractUser`. The Cedar principal type is always
`User`, regardless of the model's class name.
```
with:
```markdown
Any user model works, including custom `AUTH_USER_MODEL` classes. The Cedar
principal type is your user model's class name (e.g. `Member::"5"` for a
`Member` model; `User::"5"` with Django's default model). The `is_staff` and
`is_superuser` attributes and `Group` parent entities are included when your
model provides them — a bare `AbstractBaseUser` model gets just `id` plus any
provider-supplied attributes.
```

- [ ] **Step 2: Update `CHANGELOG.md`**

Insert between `## [Unreleased]` and `## [0.1.0] - 2026-07-11`:
```markdown
## [0.2.0] - TBD

### Changed

- The Cedar principal type is now the user model's class name via
  `get_user_model()` (previously hardcoded `User`). Breaking only for
  projects with a custom user model — where 0.1.x principal/resource
  naming was inconsistent — and a no-op for projects using Django's
  default `User`.
- `is_staff`/`is_superuser` principal attributes and `Group` parent
  entities are now capability-detected, so user models without them
  (e.g. bare `AbstractBaseUser`) are supported.
```

(`TBD` is intentional; Task 4 dates it.)

- [ ] **Step 3: Bump the version and refresh the lockfile**

In `pyproject.toml`, change `version = "0.1.0"` to `version = "0.2.0"`, then run `uv lock` (updates the package's own version in `uv.lock`).

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest -q
uvx pre-commit run --all-files
git add README.md CHANGELOG.md pyproject.toml uv.lock
git commit -m "docs: document any-user-model support; bump version to 0.2.0

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
Expected: suite green, hooks pass.

---

### Task 4: Release 0.2.0

**Files:**
- Modify: `CHANGELOG.md` (set the release date)

**Interfaces:**
- Consumes: green main from Tasks 1–3; existing `publish.yml` + PyPI trusted publisher (already configured for this repo — no user action needed).
- Produces: `django-cedar 0.2.0` on PyPI.

- [ ] **Step 1: Date the changelog and push**

Change `## [0.2.0] - TBD` to `## [0.2.0] - <today's date, YYYY-MM-DD>`, then:
```bash
git add CHANGELOG.md
git commit -m "chore: date 0.2.0 release

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

- [ ] **Step 2: Watch CI go green on main**

```bash
gh run list --repo hyperscale-consulting/django-cedar --branch main --workflow CI --limit 1 --json databaseId --jq '.[0].databaseId'
gh run watch <that-id> --repo hyperscale-consulting/django-cedar --exit-status --interval 15
```
Expected: success. If a job fails, fix minimally, commit, push, re-watch. Do not release on red CI.

- [ ] **Step 3: Cut the release**

```bash
gh release create v0.2.0 --repo hyperscale-consulting/django-cedar \
  --title "v0.2.0" \
  --notes "Any Django user model is now supported: the Cedar principal type follows get_user_model() (your user model's class name), and is_staff/is_superuser/group entities are capability-detected. Breaking only for custom-user-model projects; no-op for Django's default User. See CHANGELOG.md."
```
Note: `publish.yml` asserts the tag matches `pyproject.toml`'s version — if it fails with a mismatch, Task 3 Step 3 was missed.

- [ ] **Step 4: Watch the publish workflow and verify PyPI**

```bash
gh run list --repo hyperscale-consulting/django-cedar --workflow "Publish to PyPI" --limit 1 --json databaseId --jq '.[0].databaseId'
gh run watch <that-id> --repo hyperscale-consulting/django-cedar --exit-status --interval 15
curl -s https://pypi.org/pypi/django-cedar/json | uv run python -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
uv run --no-project --with "django-cedar==0.2.0" python -c "import django_cedar; print('installed ok')"
```
Expected: publish success; PyPI reports `0.2.0` (retry once after ~30s if stale); fresh install prints `installed ok`.

---

## Verification (whole plan)

- `uv run pytest -q` — 94 tests green.
- `uv run ruff check . && uv run ruff format --check . && uv run pyright` — clean.
- With stock settings the principal is still `User::"<pk>"`; under `AUTH_USER_MODEL = "tests.Member"` it is `Member::"<pk>"` and a user-as-resource check matches the entity store.
- `django-cedar 0.2.0` live on PyPI.
