"""Multi-hop attribute paths on both sides of the request, and entity merging."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from django_cedar.authz import _make_entities
from django_cedar.authz import _make_principal_entities
from django_cedar.authz import _merge_entities
from django_cedar.authz import Authz
from django_cedar.authz import Entity
from django_cedar.authz import entity_ref
from django_cedar.authz import EntityRef


def _make_mock_user(pk: Any = 1):
    user = MagicMock()
    user.pk = pk
    user.is_authenticated = True
    user.is_staff = False
    user.is_superuser = False
    user.groups.all.return_value = []
    return user


class Node:
    """A stand-in model: optional scalar attrs plus an optional next hop."""

    def __init__(self, pk, nxt=None, declare=True, **scalars):
        self.pk = pk
        self.nxt = nxt
        self.declare = declare
        self.scalars = scalars

    def authz_fields(self):
        fields = dict(self.scalars)
        if self.nxt is not None:
            fields["nxt"] = entity_ref(self.nxt)
        return fields

    def authz_related_entities(self):
        return [self.nxt] if self.nxt is not None and self.declare else []


# Distinct class names per level so each hop is a different entity type, like
# real models.
LEVELS: list[Any] = [type(f"Level{i}", (Node,), {}) for i in range(8)]


def _chain(depth, break_at=None) -> Any:
    """Build Level0 -> ... -> Level<depth>; the last node has flag="yes"."""
    node = LEVELS[depth](depth, flag="yes")
    for i in range(depth - 1, -1, -1):
        node = LEVELS[i](i, nxt=node, declare=(i != break_at))
    return node


class _ProfileProvider:
    """Exposes ``principal.link`` and hands the linked model to the walk."""

    def __init__(self, linked):
        self.linked = linked

    def get_attributes(self, user):
        return {"link": entity_ref(self.linked)}

    def get_entities(self, user):
        return [self.linked]


class _EntityProvider:
    """A 0.3.0-style provider that hand-builds ``Entity`` objects."""

    def __init__(self, attributes, entities):
        self.attributes = attributes
        self.entities = entities

    def get_attributes(self, user):
        return self.attributes

    def get_entities(self, user):
        return self.entities


def _path(root, hops):
    return root + ".nxt" * hops + ".flag"


class TestResourceChains:
    @pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
    def test_resource_chain_resolves(self, depth):
        path = _path("resource", depth)
        policy = f'permit(principal, action, resource) when {{ {path} == "yes" }};'
        authz = Authz(policies=policy)
        authz.authorize(_make_mock_user(), "View", _chain(depth))

    def test_cycle_terminates_and_resolves(self):
        root = _chain(4)
        leaf = root.nxt.nxt.nxt.nxt
        leaf.nxt = root  # leaf -> root closes the loop
        entities = _make_entities(root, [])
        assert len({e.ref for e in entities}) == 5
        policy = (
            "permit(principal, action, resource) "
            'when { resource.nxt.nxt.nxt.nxt.flag == "yes" };'
        )
        Authz(policies=policy).authorize(_make_mock_user(), "View", root)


class TestPrincipalChains:
    @pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
    def test_principal_chain_resolves(self, depth):
        # depth hops: principal.link is hop 1, then .nxt for the rest.
        path = "principal.link" + ".nxt" * (depth - 1) + ".flag"
        policy = f'permit(principal, action, resource) when {{ {path} == "yes" }};'
        authz = Authz(
            policies=policy,
            principal_attribute_providers=[_ProfileProvider(_chain(depth - 1))],
        )
        authz.authorize(_make_mock_user(), "View", None)

    def test_principal_chain_denies_on_wrong_value(self):
        policy = (
            "permit(principal, action, resource) "
            'when { principal.link.nxt.flag == "no" };'
        )
        authz = Authz(
            policies=policy,
            principal_attribute_providers=[_ProfileProvider(_chain(1))],
        )
        with pytest.raises(PermissionDenied):
            authz.authorize(_make_mock_user(), "View", None)

    def test_principal_cycle_terminates(self):
        root = _chain(3)
        root.nxt.nxt.nxt.nxt = root
        entities = _make_principal_entities(_make_mock_user(), [_ProfileProvider(root)])
        assert {e.ref.type for e in entities} == {
            "User",
            "Level0",
            "Level1",
            "Level2",
            "Level3",
        }

    def test_principal_and_resource_share_a_walk(self):
        # Both sides reach the same Level1 node; it is built once and both
        # paths resolve through it.
        shared = _chain(1).nxt
        resource = LEVELS[0](100, nxt=shared)
        profile = LEVELS[0](200, nxt=shared)
        policy = """
        permit(principal, action, resource)
        when { principal.link.nxt.flag == "yes" && resource.nxt.flag == "yes" };
        """
        authz = Authz(
            policies=policy,
            principal_attribute_providers=[_ProfileProvider(profile)],
        )
        authz.authorize(_make_mock_user(), "View", resource)


@pytest.mark.django_db
class TestUsersMidChain:
    def test_resource_chain_continues_through_a_user(self):
        # resource.owner is a user; the walk continues on the principal side
        # through the providers' related models to owner.link.nxt.flag.
        User = get_user_model()
        owner = User.objects.create(username="owner")
        resource = LEVELS[0](1)
        resource.authz_fields = lambda: {"owner": entity_ref(owner)}
        resource.authz_related_entities = lambda: [owner]
        policy = (
            "permit(principal, action, resource) "
            'when { resource.owner.link.nxt.flag == "yes" };'
        )
        authz = Authz(
            policies=policy,
            principal_attribute_providers=[_ProfileProvider(_chain(1))],
        )
        authz.authorize(_make_mock_user(pk=999), "View", resource)

    def test_principal_reached_from_resource_is_built_once(self):
        # Providers may query the database; reaching the principal again from
        # the resource side must not re-run them.
        User = get_user_model()
        user = User.objects.create(username="me")
        resource = LEVELS[0](1)
        resource.authz_fields = lambda: {"owner": entity_ref(user)}
        resource.authz_related_entities = lambda: [user]
        provider = MagicMock()
        provider.get_attributes.return_value = {}
        provider.get_entities.return_value = []
        authz = Authz(
            policies=(
                "permit(principal, action, resource) "
                "when { resource.owner == principal };"
            ),
            principal_attribute_providers=[provider],
        )
        authz.authorize(user, "View", resource)
        provider.get_attributes.assert_called_once_with(user)
        provider.get_entities.assert_called_once_with(user)

    def test_cycle_back_to_the_principal_terminates(self):
        # principal.link -> Level0 -> the principal again.
        User = get_user_model()
        user = User.objects.create(username="me")
        profile = LEVELS[0](1)
        profile.authz_fields = lambda: {"user": entity_ref(user)}
        profile.authz_related_entities = lambda: [user]
        authz = Authz(
            policies=(
                "permit(principal, action, resource) "
                "when { principal.link.user == principal };"
            ),
            principal_attribute_providers=[_ProfileProvider(profile)],
        )
        authz.authorize(user, "View", None)


class TestEntityProvidersBackwardCompatible:
    def test_entity_returning_provider_still_works(self):
        org = Entity(EntityRef("Organisation", "3"), attrs={"plan": "pro"})
        provider = _EntityProvider(
            {"organisation": {"__entity": {"type": "Organisation", "id": "3"}}},
            [org],
        )
        authz = Authz(
            policies=(
                "permit(principal, action, resource) "
                'when { principal.organisation.plan == "pro" };'
            ),
            principal_attribute_providers=[provider],
        )
        authz.authorize(_make_mock_user(), "View", None)

    def test_provider_may_mix_entities_and_models(self):
        org = Entity(EntityRef("Organisation", "3"), attrs={"plan": "pro"})
        provider = _EntityProvider(
            {
                "organisation": {"__entity": {"type": "Organisation", "id": "3"}},
                "link": entity_ref(_chain(1)),
            },
            [org, _chain(1)],
        )
        policy = """
        permit(principal, action, resource)
        when { principal.organisation.plan == "pro"
               && principal.link.nxt.flag == "yes" };
        """
        authz = Authz(policies=policy, principal_attribute_providers=[provider])
        authz.authorize(_make_mock_user(), "View", None)

    def test_provider_without_get_entities(self):
        provider = MagicMock(spec=["get_attributes"])
        provider.get_attributes.return_value = {"role": "admin"}
        authz = Authz(
            policies=(
                "permit(principal, action, resource) "
                'when { principal.role == "admin" };'
            ),
            principal_attribute_providers=[provider],
        )
        authz.authorize(_make_mock_user(), "View", None)


class TestDuplicateMerge:
    def test_principal_thin_copy_no_longer_hides_resource_attrs(self):
        # 0.3.0 kept the provider's thin Organisation and dropped the resource
        # walk's richer copy, so resource.org.organisation_type was missing.
        thin = Entity(EntityRef("Organisation", "3"), attrs={"name": "Acme"})
        provider = _EntityProvider(
            {"org": {"__entity": {"type": "Organisation", "id": "3"}}}, [thin]
        )
        Organisation = type("Organisation", (Node,), {})
        resource = LEVELS[0](1)
        org = Organisation(3, organisation_type="charity", name="Acme")
        resource.authz_fields = lambda: {"org": entity_ref(org)}
        resource.authz_related_entities = lambda: [org]
        policy = """
        permit(principal, action, resource)
        when { resource.org.organisation_type == "charity"
               && principal.org == resource.org };
        """
        authz = Authz(policies=policy, principal_attribute_providers=[provider])
        authz.authorize(_make_mock_user(), "View", resource)

    def test_attrs_merge_and_parents_union(self):
        ref = EntityRef("Organisation", "3")
        first = Entity(
            ref,
            attrs={"a": 1, "rec": {"x": 1}},
            parents={EntityRef("Group", "g1")},
        )
        second = Entity(
            ref,
            attrs={"b": 2, "rec": {"y": 2}},
            parents={EntityRef("Group", "g2")},
        )
        [merged] = _merge_entities([first, second])
        assert merged.attrs == {"a": 1, "b": 2, "rec": {"x": 1, "y": 2}}
        assert merged.parents == {EntityRef("Group", "g1"), EntityRef("Group", "g2")}

    def test_first_value_wins_on_conflict(self, caplog):
        ref = EntityRef("Organisation", "secret-id")
        first = Entity(ref, attrs={"name": "first", "rec": {"x": 1}})
        second = Entity(ref, attrs={"name": "second", "rec": {"x": 2}})
        with caplog.at_level("WARNING", logger="django_cedar.authz"):
            [merged] = _merge_entities([first, second])
        assert merged.attrs == {"name": "first", "rec": {"x": 1}}
        assert "Organisation" in caplog.text
        assert "name" in caplog.text and "rec.x" in caplog.text
        assert "secret-id" not in caplog.text
        assert "second" not in caplog.text

    def test_entity_refs_are_not_merged_field_by_field(self):
        ref = EntityRef("Task", "1")
        first = Entity(ref, attrs={"owner": {"__entity": {"type": "User", "id": "1"}}})
        second = Entity(
            ref, attrs={"owner": {"__entity": {"type": "User", "id": "2"}, "x": 1}}
        )
        [merged] = _merge_entities([first, second])
        assert merged.attrs == {"owner": {"__entity": {"type": "User", "id": "1"}}}

    def test_merge_does_not_mutate_inputs(self):
        ref = EntityRef("Organisation", "3")
        first_attrs = {"rec": {"x": 1}}
        first = Entity(ref, attrs=first_attrs)
        second = Entity(ref, attrs={"rec": {"y": 2}, "b": 2})
        _merge_entities([first, second])
        assert first_attrs == {"rec": {"x": 1}}

    def test_hand_built_entity_wins_over_model_on_conflict(self):
        # Hand-built provider entities come first, as they did in 0.3.0, so an
        # existing value never changes; the model only fills in what's missing.
        thin = Entity(EntityRef("Level0", "1"), attrs={"flag": "hand-built"})
        provider = _EntityProvider({}, [thin])
        authz = Authz(
            policies=(
                "permit(principal, action, resource) "
                'when { resource.flag == "hand-built" && resource.extra == "model" };'
            ),
            principal_attribute_providers=[provider],
        )
        authz.authorize(
            _make_mock_user(), "View", LEVELS[0](1, flag="model", extra="model")
        )


class TestEntityRefHelper:
    def test_model_ref(self):
        assert entity_ref(LEVELS[0](7)) == {"__entity": {"type": "Level0", "id": "7"}}

    @pytest.mark.django_db
    def test_user_ref_uses_principal_type(self):
        User = get_user_model()
        user = User.objects.create(username="u")
        assert entity_ref(user) == {
            "__entity": {"type": User.__name__, "id": str(user.pk)}
        }
