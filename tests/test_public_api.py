from __future__ import annotations

import pytest


def test_public_exports_resolve():
    import django_cedar
    from django_cedar.authz import Authz
    from django_cedar.authz import create_authz
    from django_cedar.authz import Entity
    from django_cedar.authz import entity_ref
    from django_cedar.authz import EntityRef
    from django_cedar.authz import ForbidPolicyError

    assert django_cedar.Authz is Authz
    assert django_cedar.Entity is Entity
    assert django_cedar.EntityRef is EntityRef
    assert django_cedar.create_authz is create_authz
    assert django_cedar.entity_ref is entity_ref
    assert django_cedar.ForbidPolicyError is ForbidPolicyError


def test_all_matches_exports():
    import django_cedar

    assert set(django_cedar.__all__) == {
        "Authz",
        "Entity",
        "EntityRef",
        "ForbidPolicyError",
        "create_authz",
        "entity_ref",
    }


def test_unknown_attribute_raises():
    import django_cedar

    with pytest.raises(AttributeError):
        _ = django_cedar.does_not_exist
