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

    def test_provider_attributes_included_for_bare_model(self, settings):
        settings.AUTH_USER_MODEL = "tests.Device"
        policy = """
        permit(principal, action, resource)
        when { principal.role == "admin" };
        """

        class RoleProvider:
            def get_attributes(self, user):
                return {"role": "admin"}

        authz = Authz(policies=policy, principal_attribute_providers=[RoleProvider()])
        authz.authorize(Device(pk=11), "Ping", None)
