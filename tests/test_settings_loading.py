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
            "permit(principal, action, resource) when { context.allow.self_signup };"
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
