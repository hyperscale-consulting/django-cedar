# django-cedar 0.2.0: `get_user_model()`-based principals — Design

**Date:** 2026-07-11
**Status:** Approved pending final review

## Purpose

Remove the hardcoded `AbstractUser`/`User` assumption from principal
construction. Any Django user model — custom `AbstractUser` subclasses,
`AbstractBaseUser + PermissionsMixin`, or bare `AbstractBaseUser` — works,
and the Cedar principal type follows the model's class name, consistent
with how resources are named.

## Decisions

| Topic | Decision |
|---|---|
| Principal entity type | `get_user_model().__name__` (e.g. `Member::"5"`), not hardcoded `User` |
| Model support | Any user model; capabilities detected, not required |
| Anonymous principal | Unchanged: `Anonymous::"guest"` |
| Version | 0.2.0 (SemVer minor, pre-1.0; breaking only for custom-user-model projects, where 0.1.x was broken anyway) |
| Default-`User` projects | Byte-identical behavior to 0.1.x (class name is `User`) |

## Changes (`src/django_cedar/authz.py`)

1. **Principal UID**: in `Authz.authorize()`, the principal string becomes
   `_cedar_uid(get_user_model().__name__, str(user.pk))` instead of the
   hardcoded `User` type.
2. **Principal entity**: `_make_user_entities()` uses
   `EntityRef(get_user_model().__name__, str(user.pk))`.
3. **Capability-detected attributes**: attrs start as `{"id": str(pk)}`;
   `is_staff` and `is_superuser` are added only when the instance has those
   attributes (`hasattr`). Provider attrs merge as today.
4. **Capability-detected groups**: `Group` parent refs and `Group` entities
   are built only when the model has a `groups` manager (`hasattr`). The
   existing single-evaluation of `groups.all()` is preserved.
5. **User-as-resource detection**: `_make_entities()` replaces
   `isinstance(entity, AbstractUser)` with
   `isinstance(entity, get_user_model())`. (`SimpleLazyObject`-wrapped
   `request.user` passes `isinstance` transparently.) Because both principal
   and resource naming now derive from the class name, a user-model instance
   passed as a resource (e.g. `CurrentUserScopedMixin`) produces matching
   types in the request string and the entity store.
6. **Type hints**: `AbstractUser` hints at the public boundaries loosen to
   `AbstractBaseUser | None` (project's established pyright idiom: targeted
   `Any`/`cast` at dynamic Django boundaries; no django-stubs, no
   type: ignore).

`get_user_model()` is called at authorization time (it is a cheap registry
lookup); no caching is added, so `@override_settings(AUTH_USER_MODEL=...)`
in consumer test suites behaves correctly without new signal wiring.

## Testing

- Existing mock-based tests continue to cover the default-`User` path
  unchanged (mocks are not instances of the user model, so the
  `isinstance` branch keeps treating them as plain resources — as today).
- Add `tests/models.py` with two concrete models:
  - `Member(AbstractUser)` — custom full-featured user model
  - `Device(AbstractBaseUser)` — bare user model (no `is_staff`, no groups;
    `USERNAME_FIELD` set to a simple char field)
  The `tests` package (already in `INSTALLED_APPS`) gains these models;
  most tests use unsaved instances with an explicit `pk` (no database), but
  tests that exercise the `groups` manager on a real model use
  `pytest.mark.django_db` (the in-memory SQLite test database creates
  tables for migration-less apps via `run_syncdb`).
- New tests:
  - Principal UID and entity type follow `AUTH_USER_MODEL` under
    `@override_settings(AUTH_USER_MODEL="tests.Member")` (authorize against
    a policy matching `Member::"..."`).
  - Bare-model entity has only `id` (+ provider attrs), no
    `is_staff`/`is_superuser`, no parents; policies not referencing those
    attributes still authorize.
  - Full-featured custom model still gets `is_staff`/`is_superuser`/group
    parents.
  - User-model instance passed as resource: request resource type matches
    the entity-store type (regression for the 0.1.x mismatch).
  - Default-path regression: with stock settings, principal remains
    `User::"<pk>"`.

## Documentation

- README: remove the "must subclass `django.contrib.auth.models.AbstractUser`;
  principal type is always `User`" requirement note. Replace with: principal
  type is the user model's class name; `is_staff`/`is_superuser` attributes
  and `Group` parents are included when the model provides them.
- CHANGELOG 0.2.0 under **Changed**: "The Cedar principal type is now the
  user model's class name via `get_user_model()` (previously hardcoded
  `User`). Breaking only for projects with a custom user model — where
  0.1.x principal/resource naming was inconsistent — and a no-op for
  projects using Django's default `User`."

## Out of scope

- Configurable principal type name (`CEDAR_PRINCIPAL_ENTITY_TYPE`) — YAGNI.
- Changing the `Anonymous`/`Group` entity vocabulary.
- Any views.py changes (none needed — resource naming already derives from
  the class name).
