from __future__ import annotations

from typing import Any
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


def _make_mock_resource(class_name, pk=1) -> Any:
    """Create a mock resource that isn't an AbstractUser and has a proper class name."""

    class FakeModel:
        pass

    FakeModel.__name__ = class_name
    obj: Any = FakeModel()
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
