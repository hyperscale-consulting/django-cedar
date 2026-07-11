# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
