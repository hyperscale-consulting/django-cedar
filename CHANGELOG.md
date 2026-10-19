# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-10-19

### Security

- Policies that error during evaluation are no longer silent. Cedar skips a
  policy whose evaluation errors (for example, a model on an attribute path
  that doesn't declare its next hop), and a skipped `forbid` *allows* the
  request. Every skipped policy is now logged at `ERROR` with its policy id,
  effect and `@id`, with entity ids and values redacted.
- New `CEDAR_RAISE_ON_FORBID_ERROR` setting: when on, a skipped `forbid`
  raises `ForbidPolicyError` (not a `PermissionDenied` subclass) instead of
  allowing. **On by default under `DEBUG` and test runners**, so test suites
  with a `forbid` that errors — including one that reads an attribute the
  user model doesn't have, which the README previously described as "never
  applies" — will now fail. Fix the policy or model (or guard with `has`),
  or set the setting to `False` to keep the old behaviour. Off by default
  otherwise; turning it on in production fails closed.

### Added

- Principal-side attribute paths of any depth, e.g.
  `principal.profile.organisation.billing_status`. A principal attribute
  provider's `get_entities(user)` may now return model instances as well as
  `Entity` objects; models are walked through `authz_fields()` /
  `authz_related_entities()` exactly like resources. Providers that return
  `Entity` objects work unchanged.
- `entity_ref(obj)` builds the Cedar entity reference for an attribute that
  points at another model (or user).
- `Authz(raise_on_forbid_error=...)` overrides the setting for one engine.

### Changed

- The principal and resource walks share one visited set: a model reached
  from both sides is built once, a cycle through the principal stops, and a
  resource chain that reaches the requesting user no longer re-runs the
  principal attribute providers.
- When the same entity arrives by more than one route its copies are merged
  (attributes recursively, parents unioned) instead of the first copy being
  kept whole. On a conflicting value the first wins, with a warning; the
  order is hand-built provider entities, the principal and groups, the
  principal's related models, then the resource walk. Values 0.3.0 produced
  are unchanged; previously dropped attributes are now present.
- The debug-level log of Cedar diagnostics on deny is replaced by the
  error-level per-policy log above.

## [0.3.0] - 2026-10-18

### Security

- A missing object in `get_resource()` (`Http404` or `ObjectDoesNotExist`)
  now raises `PermissionDenied` (403) instead of surfacing as 404 or 500,
  so a denied principal can no longer enumerate which objects exist.
  Projects relying on 404 for missing objects in `Authorized*` views
  should expect 403, or set `deny_missing_resource = False` on the view
  to keep the old behaviour.

### Changed

- Refreshed the development lockfile (Django 6.0.8, sqlparse 0.6.0) and CI
  action pins. No changes to the published package or its dependency
  constraints.
- Added `make bump` / `make release` targets for cutting releases.
- `ResourceIsCurrentObjectMixin` memoises `get_object()` so the object is
  fetched once per request instead of twice (once for authorization, once
  by the Django handler).

## [0.2.0] - 2026-07-11

### Changed

- The Cedar principal type is now the user model's class name via
  `get_user_model()` (previously hardcoded `User`). Breaking only for
  projects with a custom user model — where 0.1.x principal/resource
  naming was inconsistent — and a no-op for projects using Django's
  default `User`.
- `is_staff`/`is_superuser` principal attributes and `Group` parent
  entities are now capability-detected, so user models without them
  (e.g. bare `AbstractBaseUser`) are supported.

## [0.1.0] - 2026-07-11

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
