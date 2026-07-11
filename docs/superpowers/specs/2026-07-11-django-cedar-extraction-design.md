# django-cedar: Extraction & Open-Source Packaging — Design

**Date:** 2026-07-11
**Status:** Approved pending final review

## Purpose

Extract the `django_cedar` app from `hyperscale/app-studio` into a standalone
open-source package, published to PyPI as **`django-cedar`**, so any Django
project can use [Cedar](https://www.cedarpolicy.com/) policy-based
authorization. Migrating app-studio to consume the published package is a
separate follow-up project, out of scope here.

## Decisions

| Topic | Decision |
|---|---|
| PyPI name | `django-cedar` (confirmed available), import `django_cedar` |
| Repo | `hyperscale-consulting/django-cedar` (public) |
| License | Apache-2.0 |
| Python | 3.12, 3.13, 3.14 |
| Django | 5.2 LTS and 6.0 |
| Integration style | Plain library + optional `INSTALLED_APPS` entry for system checks |
| Tooling | uv project, `uv_build` backend, ruff, pyright, pytest + pytest-django, pre-commit |
| Releases | GitHub Release (tag `vX.Y.Z`) triggers publish via PyPI Trusted Publishing; start at 0.1.0 |
| App-studio couplings | Generalized (see API changes) |

## Package structure

```
src/django_cedar/
    __init__.py      # public API re-exports
    apps.py          # optional AppConfig — registers system checks
    checks.py        # Django system checks (new)
    authz.py         # Authz engine, entity construction, settings loading
    views.py         # CedarAuthorizationMixin, Authorized* views, scoping mixins
tests/
docs/
.github/workflows/
```

Runtime dependencies: `django>=5.2`, `cedarpy>=4.8.1`.

## Public API

From `django_cedar`: `Authz`, `create_authz`, `Entity`, `EntityRef`.
From `django_cedar.views`: `CedarAuthorizationMixin`,
`ResourceIsCurrentObjectMixin`, `CurrentUserScopedMixin`,
`AsyncLoginRequiredMixin`, `AuthorizedDetailView`, `AuthorizedListView`,
`AuthorizedCreateView`, `AuthorizedUpdateView`, `AuthorizedDeleteView`,
`AuthorizedTemplateView`, `AuthorizedFormView`.

Model protocols carry over unchanged: models may define `authz_fields()`
(entity attributes) and `authz_related_entities()` (related models included
transitively so Cedar can resolve attribute chains).

### Settings

- `CEDAR_POLICY_PATH` (required): path to the Cedar policy file. Relative
  paths resolve against `settings.BASE_DIR` (falling back to `Path.cwd()` if
  `BASE_DIR` is unset); absolute paths used as-is.
- `CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS` (optional): list of dotted paths to
  classes providing `get_attributes(user) -> dict` and optionally
  `get_entities(user) -> iterable[Entity]`. Unchanged from the original.
- `CEDAR_CONTEXT_PROVIDERS` (optional, **new**): list of dotted paths to
  classes providing `get_context(user, action, resource) -> dict`. Results
  are deep-merged into the Cedar request context (providers in listed order,
  then any per-call `context=` argument merged last, winning conflicts).

## Changes from the app-studio code

1. **Remove `ALLOW_SELF_SIGNUP`** from the hardcoded Cedar context. The
   built-in context becomes empty; apps supply context via
   `CEDAR_CONTEXT_PROVIDERS`. (App-studio will later add a one-class provider
   returning `{"allow": {"self_signup": ...}}`.)
2. **`OrganisationScopedMixin` is not extracted** — its
   `user.profile.organisation` assumption is app-studio-specific. The README
   documents overriding `get_resource()` for custom scoping instead.
3. **Policy path resolution** switches from `Path.cwd()` to
   `settings.BASE_DIR` for relative paths (Django convention).
4. **Rename `Model` → `Entity`** (dataclass in `authz.py`). `Model` collides
   with Django's `Model` concept. `EntityRef` keeps its name.
5. **Settings caches respect `override_settings`**: the `lru_cache`s on
   policy/provider loading are cleared via Django's `setting_changed` signal.
6. **System checks** (new, in `checks.py`, registered by the `AppConfig`):
   - `CEDAR_POLICY_PATH` not set → error
   - policy file missing/unreadable → error
   - policy file fails to parse as Cedar (via `cedarpy.format_policies`,
     which raises on syntax errors) → error
   - any configured provider dotted path fails to import or lacks the
     required method → error

   Checks only run when `django_cedar` is in `INSTALLED_APPS`; everything
   else works via plain imports without registration.

## Tooling

- **uv** project, `requires-python = ">=3.12"`, `uv_build` build backend.
- **ruff** (lint + format), **pyright** (basic mode), **pytest** +
  **pytest-django** + coverage.
- **pre-commit** mirroring app-studio's config: `ruff-check`, `ruff-format`,
  `uv-lock`, standard pre-commit-hooks; SHA-frozen revs.

## CI/CD (GitHub Actions)

`ci.yml` — on PRs and pushes to `main`:

- **lint**: `ruff check`, `ruff format --check`, `pyright`
- **test**: matrix Python {3.12, 3.13, 3.14} × Django {5.2, 6.0} (6 cells),
  pytest with coverage (reported, not gated initially)
- **build**: `uv build` + sdist/wheel metadata validation
- **security**: `pip-audit` against the lockfile; `zizmor` workflow linting

`publish.yml` — on GitHub Release published:

- Build sdist + wheel, publish via **PyPI Trusted Publishing** (OIDC, no API
  tokens), gated through a `pypi` GitHub environment.
- Version lives in `pyproject.toml`. Flow: bump version + changelog → tag
  `vX.Y.Z` → publish GitHub Release → workflow publishes to PyPI.

All third-party actions pinned to commit SHAs; least-privilege
`permissions:` blocks on every workflow.

### GitHub security configuration (free on public repos)

- CodeQL default setup (Python)
- Secret scanning + push protection
- Dependabot: alerts, security updates, and `dependabot.yml` for weekly
  `pip` + `github-actions` update PRs
- Private vulnerability reporting enabled; `SECURITY.md` points at it

### Manual step (user)

Create a **pending trusted publisher** on PyPI before the first release:
project `django-cedar`, owner `hyperscale-consulting`, repository
`django-cedar`, workflow `publish.yml`, environment `pypi`.

## Testing strategy

- Port the existing tests (`test_authz.py`, `test_views.py`, ~540 lines) with
  import/rename updates only.
- New tests: `CEDAR_CONTEXT_PROVIDERS` (provider order, deep-merge semantics,
  per-call context winning), `BASE_DIR`-relative path resolution, cache
  invalidation under `override_settings`, and each system check (fires on
  misconfiguration, silent when correct, skipped when app not installed).
- Minimal `tests/settings.py`; no database unless a test requires one.

## Documentation & repo hygiene

- **README.md**: what Cedar is, install, quickstart (settings + policy file +
  one `AuthorizedDetailView` example), settings reference, model protocols,
  custom `get_resource()` scoping, async view support.
- **CHANGELOG.md** (Keep a Changelog), **LICENSE** (Apache-2.0),
  **SECURITY.md**, **CONTRIBUTING.md** (uv + pre-commit setup, running the
  matrix locally).
- PyPI trove classifiers for the supported Python/Django versions; project
  URLs → GitHub repo.

## Repo conventions

- Commits signed (repo-local `user.signingkey` configured;
  `commit.gpgsign=true` globally). Author email
  `andy@hyperscale.consulting`.
