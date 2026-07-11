from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import cast

from cedarpy import is_authorized
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import PermissionDenied
from django.core.signals import setting_changed
from django.db.models import Model as DjangoModel

logger = logging.getLogger(__name__)


def _cedar_uid(entity_type: str, entity_id: str) -> str:
    """Build a Cedar entity UID string with the id safely escaped.

    Cedar string literals use ``\\`` and ``"`` as escape characters, so an id
    containing either would otherwise produce a malformed request string.
    Only the request string is escaped; the entity dicts keep RAW ids because
    cedarpy unescapes the request string before matching.
    """
    escaped = entity_id.replace("\\", "\\\\").replace('"', '\\"')
    return f'{entity_type}::"{escaped}"'


def _principal_type() -> str:
    return get_user_model().__name__


def _entity_type(obj: Any) -> str:
    if isinstance(obj, get_user_model()):
        return _principal_type()
    return type(obj).__name__


def _resolve_policy_path() -> Path:
    raw = settings.CEDAR_POLICY_PATH
    p = Path(raw).expanduser()
    if not p.is_absolute():
        base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        p = base / p
    return p.resolve()


def _get_policy_path() -> Path:
    p = _resolve_policy_path()
    if not p.is_file():
        raise FileNotFoundError(f"Policy file not found at {p}")
    return p


@lru_cache(maxsize=1)
def get_policies() -> str:
    return _get_policy_path().read_text()


def import_from_path(path: str):
    try:
        module_path, attr = path.rsplit(".", 1)
    except ValueError as e:
        raise ImproperlyConfigured(
            f"Invalid provider path '{path}'. Expected 'some.module.ClassName'."
        ) from e

    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as e:
        raise ImproperlyConfigured(
            f"Provider '{path}' not found (no attribute '{attr}' in '{module_path}')."
        ) from e


def _load_providers(setting_name: str) -> list[Any]:
    paths = getattr(settings, setting_name, [])
    if not isinstance(paths, (list, tuple)):
        raise ImproperlyConfigured(f"{setting_name} must be a list/tuple.")
    return [import_from_path(p)() for p in paths]


@lru_cache(maxsize=1)
def get_principal_attr_providers() -> list[Any]:
    return _load_providers("CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS")


@lru_cache(maxsize=1)
def get_context_providers() -> list[Any]:
    return _load_providers("CEDAR_CONTEXT_PROVIDERS")


_SETTING_CACHES = {
    "CEDAR_POLICY_PATH": (get_policies,),
    "BASE_DIR": (get_policies,),
    "CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS": (get_principal_attr_providers,),
    "CEDAR_CONTEXT_PROVIDERS": (get_context_providers,),
}


def _clear_caches_on_setting_change(*, setting, **kwargs) -> None:
    for fn in _SETTING_CACHES.get(setting, ()):
        fn.cache_clear()


setting_changed.connect(
    _clear_caches_on_setting_change,
    dispatch_uid="django_cedar.authz.clear_caches",
)


def create_authz() -> Authz:
    return Authz(
        policies=get_policies(),
        principal_attribute_providers=get_principal_attr_providers(),
        context_providers=get_context_providers(),
    )


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
        user: AbstractBaseUser | None,
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
            and _cedar_uid(_entity_type(resource), str(resource.pk))
            or 'System::"global"'
        )
        principal = 'Anonymous::"guest"'
        if user and user.is_authenticated:
            principal = _cedar_uid(_principal_type(), str(user.pk))
        cedar_action = _cedar_uid("Action", action)
        cedar_context: dict[str, Any] = {}
        for provider in self.context_providers:
            _deep_merge(cedar_context, provider.get_context(user, action, resource))
        if context:
            _deep_merge(cedar_context, context)
        authz_request = dict(
            principal=principal,
            action=cedar_action,
            resource=cedar_resource,
            context=cedar_context,
        )
        logger.debug(f"Entities:\n {json.dumps(entity_dicts, indent=2)}")
        logger.debug(f"AuthRequest:\n {json.dumps(authz_request, indent=2)}")
        authz_result = is_authorized(authz_request, self.policies, entity_dicts)
        if not authz_result.allowed:
            logger.debug(f"AuthzResult errors: {authz_result.diagnostics.errors}")
            logger.info(
                f"Authz denied: principal={principal} action={cedar_action} "
                f"resource={cedar_resource}"
            )
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
    user: AbstractBaseUser, principal_attribute_providers: list[Any]
) -> set[Entity]:
    user_groups: Any = getattr(user, "groups", None)
    groups = list(user_groups.all()) if user_groups is not None else []
    result = set()
    attrs: dict[str, Any] = {"id": str(user.pk)}
    for flag in ("is_staff", "is_superuser"):
        if hasattr(user, flag):
            attrs[flag] = getattr(user, flag)
    for provider in principal_attribute_providers:
        attrs.update(provider.get_attributes(user))
        if hasattr(provider, "get_entities"):
            result.update(provider.get_entities(user))

    result.add(
        Entity(
            EntityRef(_principal_type(), str(user.pk)),
            attrs=attrs,
            parents={EntityRef("Group", group.name) for group in groups},
        )
    )
    for group in groups:
        result.add(
            Entity(
                EntityRef("Group", group.name),
                attrs={"id": str(group.pk)},
            )
        )
    return result


def _make_principal_entities(
    user: AbstractBaseUser | None, principal_attribute_providers: list[Any]
) -> set[Entity]:
    if not user or not user.is_authenticated:
        return {Entity(EntityRef("Anonymous", "guest"))}

    return _make_user_entities(user, principal_attribute_providers)


def _make_entities(
    entity: Any,
    principal_attribute_providers: list[Any],
    seen: set[EntityRef] | None = None,
) -> set[Entity]:
    if isinstance(entity, get_user_model()):
        return _make_principal_entities(entity, principal_attribute_providers)

    if seen is None:
        seen = set()

    ref = EntityRef(type(entity).__name__, str(entity.pk))
    if ref in seen:
        return set()
    seen.add(ref)

    result = set()

    attrs: dict[str, Any] = {}
    authz_fields = getattr(entity, "authz_fields", None)
    if callable(authz_fields):
        attrs = cast("dict[str, Any]", authz_fields())

    attrs["id"] = str(entity.pk)
    result.add(Entity(ref, attrs=attrs))

    # Transitively include any entities the model declares as related so Cedar
    # can resolve `resource.foo.bar` attribute chains. Models opt in by
    # defining `authz_related_entities()` → iterable of related Django models.
    # ``seen`` guards against cycles (A → B → A) that would otherwise recurse
    # unboundedly.
    related_fn = getattr(entity, "authz_related_entities", None)
    if callable(related_fn):
        for related in cast("Iterable[Any]", related_fn() or ()):
            result.update(_make_entities(related, principal_attribute_providers, seen))

    return result


def _deep_merge(dst: dict[str, Any], src: Mapping[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, Mapping) and isinstance(dst.get(k), Mapping):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst
