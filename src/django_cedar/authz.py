from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import cast

from cedarpy import is_authorized
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db.models import Model as DjangoModel

logger = logging.getLogger(__name__)


class Authz:
    def __init__(
        self,
        policies: str,
        principal_attribute_providers: list[Any] | None = None,
        context_providers: list[Any] | None = None,
    ):
        self.policies = policies
        self.principal_attribute_providers = principal_attribute_providers or []
        self.context_providers = context_providers or []

    def authorize(
        self,
        user: AbstractUser | None,
        action: str,
        resource: DjangoModel | None,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        entities = _make_principal_entities(
            user, principal_attribute_providers=self.principal_attribute_providers
        )
        if resource:
            entities.update(
                _make_entities(resource, self.principal_attribute_providers)
            )
        entity_dicts = [e.to_dict() for e in entities]
        cedar_resource = (
            resource
            and f'{type(resource).__name__}::"{resource.pk}"'
            or 'System::"global"'
        )
        principal = 'Anonymous::"guest"'
        if user and user.is_authenticated:
            principal = f'User::"{str(user.pk)}"'
        cedar_context: dict[str, Any] = {}
        for provider in self.context_providers:
            _deep_merge(cedar_context, provider.get_context(user, action, resource))
        if context:
            _deep_merge(cedar_context, context)
        authz_request = dict(
            principal=principal,
            action=f'Action::"{action}"',
            resource=cedar_resource,
            context=cedar_context,
        )
        logger.debug(f"Entities:\n {json.dumps(entity_dicts, indent=2)}")
        logger.debug(f"AuthRequest:\n {json.dumps(authz_request, indent=2)}")
        authz_result = is_authorized(authz_request, self.policies, entity_dicts)
        if not authz_result.allowed:
            logger.debug(f"AuthzResult errors: {authz_result.diagnostics.errors}")
            logger.info(f"Authz denied: {authz_request}")
            raise PermissionDenied("Forbidden")


@dataclass(frozen=True)
class EntityRef:
    type: str
    id: str

    def to_dict(self) -> dict:
        return dict(type=self.type, id=self.id)


@dataclass(frozen=True)
class Entity:
    ref: EntityRef
    attrs: dict[str, Any] = field(default_factory=dict)
    parents: set[EntityRef] = field(default_factory=set)

    def __hash__(self):
        return hash((self.ref.type, self.ref.id))

    def __eq__(self, value):
        return isinstance(value, Entity) and self.ref == value.ref

    @staticmethod
    def create(type: str, id: str) -> Entity:
        return Entity(EntityRef(type, id))

    def to_dict(self) -> dict:
        return {
            "uid": {"__entity": self.ref.to_dict()},
            "attrs": self.attrs,
            "parents": [p.to_dict() for p in self.parents],
        }


def _make_user_entities(
    user: AbstractUser, principal_attribute_providers: list[Any]
) -> set[Entity]:
    user_groups: Any = user.groups
    result = set()
    attrs = {
        "id": str(user.pk),
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }
    for provider in principal_attribute_providers:
        attrs.update(provider.get_attributes(user))
        if hasattr(provider, "get_entities"):
            result.update(provider.get_entities(user))

    result.add(
        Entity(
            EntityRef("User", str(user.pk)),
            attrs=attrs,
            parents={EntityRef("Group", group.name) for group in user_groups.all()},
        )
    )
    for group in user_groups.all():
        result.add(
            Entity(
                EntityRef("Group", group.name),
                attrs={"id": str(group.pk)},
            )
        )
    return result


def _make_principal_entities(
    user: AbstractUser | None, principal_attribute_providers: list[Any]
) -> set[Entity]:
    if not user or not user.is_authenticated:
        return {Entity(EntityRef("Anonymous", "guest"))}

    return _make_user_entities(user, principal_attribute_providers)


def _make_entities(
    entity: Any, principal_attribute_providers: list[Any]
) -> set[Entity]:
    if isinstance(entity, AbstractUser):
        return _make_principal_entities(entity, principal_attribute_providers)

    result = set()

    attrs: dict[str, Any] = {}
    authz_fields = getattr(entity, "authz_fields", None)
    if callable(authz_fields):
        attrs = cast("dict[str, Any]", authz_fields())

    attrs["id"] = str(entity.pk)
    result.add(
        Entity(
            EntityRef(type(entity).__name__, str(entity.pk)),
            attrs=attrs,
        )
    )

    # Transitively include any entities the model declares as related so Cedar
    # can resolve `resource.foo.bar` attribute chains. Models opt in by
    # defining `authz_related_entities()` → iterable of related Django models.
    related_fn = getattr(entity, "authz_related_entities", None)
    if callable(related_fn):
        for related in cast("Iterable[Any]", related_fn() or ()):
            result.update(_make_entities(related, principal_attribute_providers))

    return result


def _deep_merge(dst: dict[str, Any], src: Mapping[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, Mapping) and isinstance(dst.get(k), Mapping):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst
