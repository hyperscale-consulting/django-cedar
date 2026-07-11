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
