# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
