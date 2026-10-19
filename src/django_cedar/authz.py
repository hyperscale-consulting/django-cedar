from __future__ import annotations

import importlib
import json
import logging
import re
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import cast

from cedarpy import is_authorized
from cedarpy import policies_to_json_str
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core import mail
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


def entity_ref(obj: Any) -> dict[str, Any]:
    """Return a Cedar entity reference to a model instance.

    Use it in ``authz_fields()`` or a provider's ``get_attributes()`` for an
    attribute that policies follow to another entity, as in
    ``resource.project.owner``. The referenced instance must also reach the
    request through ``authz_related_entities()`` or a provider's
    ``get_entities()``.
    """
    return {"__entity": {"type": _entity_type(obj), "id": str(obj.pk)}}


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


class ForbidPolicyError(Exception):
    """A ``forbid`` policy errored during evaluation, so Cedar skipped it.

    Raised when ``CEDAR_RAISE_ON_FORBID_ERROR`` is on. Deliberately not a
    ``PermissionDenied``: a skipped deny is a bug in the policies or the
    models feeding them, and must not pass for an ordinary 403.
    """


def _raise_on_forbid_error_setting() -> bool:
    configured = getattr(settings, "CEDAR_RAISE_ON_FORBID_ERROR", None)
    if configured is not None:
        return bool(configured)
    # On under DEBUG and under test runners: Django's runner and pytest-django
    # both call setup_test_environment(), which installs mail.outbox.
    return bool(settings.DEBUG) or hasattr(mail, "outbox")


# cedarpy reports each per-policy error as a string of this form.
_POLICY_ERROR = re.compile(r"error while evaluating policy `([^`]+)`: (.*)", re.S)
# Entity UIDs and string literals in the reason can carry user data.
_REDACT = (
    (re.compile(r"`[^`]*::[^`]*`"), "`<entity>`"),
    (re.compile(r'"(?:[^"\\]|\\.)*"'), '"<redacted>"'),
)


@lru_cache(maxsize=8)
def _policy_effects(policies: str) -> dict[str, tuple[str, str | None]]:
    """Map Cedar's policy ids to ``(effect, @id annotation)``."""
    try:
        parsed = json.loads(policies_to_json_str(policies))
    except Exception:  # cedarpy raises on any parse failure
        return {}
    return {
        policy_id: (policy["effect"], policy.get("annotations", {}).get("id"))
        for policy_id, policy in parsed.get("staticPolicies", {}).items()
    }


def _redact(reason: str) -> str:
    for pattern, replacement in _REDACT:
        reason = pattern.sub(replacement, reason)
    return reason


class Authz:
    def __init__(
        self,
        policies: str,
        principal_attribute_providers: list[Any] | None = None,
        context_providers: list[Any] | None = None,
        *,
        raise_on_forbid_error: bool | None = None,
    ):
        self.policies = policies
        self.principal_attribute_providers = principal_attribute_providers or []
        self.context_providers = context_providers or []
        # None defers to the CEDAR_RAISE_ON_FORBID_ERROR setting per request.
        self.raise_on_forbid_error = raise_on_forbid_error

    def authorize(
        self,
        user: AbstractBaseUser | None,
        action: str,
        resource: DjangoModel | None,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        # One walk across both sides: a model reached from the principal and
        # from the resource is built once.
        seen: set[EntityRef] = set()
        entities = _make_principal_entities(
            user, self.principal_attribute_providers, seen
        )
        if resource:
            entities.extend(
                _make_entities(resource, self.principal_attribute_providers, seen)
            )
        entity_dicts = [e.to_dict() for e in _merge_entities(entities)]
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
        self._check_evaluation_errors(authz_result.diagnostics.errors, action)
        if not authz_result.allowed:
            logger.info(
                f"Authz denied: principal={principal} action={cedar_action} "
                f"resource={cedar_resource}"
            )
            raise PermissionDenied("Forbidden")

    def _check_evaluation_errors(self, errors: Iterable[str], action: str) -> None:
        """Log each policy Cedar skipped for erroring; raise for skipped forbids.

        Cedar ignores a policy whose evaluation errors (an attribute or entity
        the request doesn't supply, a type mismatch). For a ``permit`` that
        only denies, but for a ``forbid`` it allows what the policy meant to
        deny. Logs carry the policy id, effect and ``@id`` but no entity ids
        or values.
        """
        effects = _policy_effects(self.policies) if errors else {}
        skipped_forbids: list[str] = []
        for message in errors:
            match = _POLICY_ERROR.match(message)
            if match:
                policy_id, reason = match.group(1), _redact(match.group(2))
            else:
                policy_id, reason = "<unknown>", "unrecognised cedarpy error"
            effect, annotation = effects.get(policy_id, (None, None))
            label = (
                policy_id if annotation is None else f'{policy_id} @id("{annotation}")'
            )
            logger.error(
                "Cedar skipped %s policy %s for action %s: it errored during "
                "evaluation (%s)",
                effect or "unknown-effect",
                label,
                action,
                reason,
            )
            # An error we can't attribute to a permit might be a skipped deny.
            if effect != "permit":
                skipped_forbids.append(label)

        raise_on_error = self.raise_on_forbid_error
        if raise_on_error is None:
            raise_on_error = _raise_on_forbid_error_setting()
        if skipped_forbids and raise_on_error:
            raise ForbidPolicyError(
                "Cedar skipped forbid policies that errored during evaluation: "
                + ", ".join(skipped_forbids)
                + ". Check that every model on their attribute paths declares "
                "its next hop in authz_related_entities() or get_entities()."
            )


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
    user: AbstractBaseUser,
    principal_attribute_providers: list[Any],
    seen: set[EntityRef],
) -> list[Entity]:
    ref = EntityRef(_principal_type(), str(user.pk))
    if ref in seen:
        return []
    seen.add(ref)

    user_groups: Any = getattr(user, "groups", None)
    groups = list(user_groups.all()) if user_groups is not None else []
    attrs: dict[str, Any] = {"id": str(user.pk)}
    for flag in ("is_staff", "is_superuser"):
        if hasattr(user, flag):
            attrs[flag] = getattr(user, flag)
    # Providers' get_entities() may return hand-built Entity objects, which
    # are used as-is, and model instances, which are walked like resources.
    hand_built: list[Entity] = []
    related: list[Any] = []
    for provider in principal_attribute_providers:
        attrs.update(provider.get_attributes(user))
        get_entities = getattr(provider, "get_entities", None)
        if callable(get_entities):
            for item in cast("Iterable[Any]", get_entities(user) or ()):
                (hand_built if isinstance(item, Entity) else related).append(item)

    # Hand-built entities go first so, as in 0.3.0, their values win any
    # conflict in _merge_entities().
    result = list(hand_built)
    result.append(
        Entity(
            ref,
            attrs=attrs,
            parents={EntityRef("Group", group.name) for group in groups},
        )
    )
    for group in groups:
        result.append(
            Entity(
                EntityRef("Group", group.name),
                attrs={"id": str(group.pk)},
            )
        )
    for model in related:
        result.extend(_make_entities(model, principal_attribute_providers, seen))
    return result


def _make_principal_entities(
    user: AbstractBaseUser | None,
    principal_attribute_providers: list[Any],
    seen: set[EntityRef] | None = None,
) -> list[Entity]:
    if not user or not user.is_authenticated:
        return [Entity(EntityRef("Anonymous", "guest"))]

    if seen is None:
        seen = set()
    return _make_user_entities(user, principal_attribute_providers, seen)


def _make_entities(
    entity: Any,
    principal_attribute_providers: list[Any],
    seen: set[EntityRef] | None = None,
) -> list[Entity]:
    if seen is None:
        seen = set()

    if isinstance(entity, get_user_model()):
        return _make_principal_entities(entity, principal_attribute_providers, seen)

    ref = EntityRef(type(entity).__name__, str(entity.pk))
    if ref in seen:
        return []
    seen.add(ref)

    attrs: dict[str, Any] = {}
    authz_fields = getattr(entity, "authz_fields", None)
    if callable(authz_fields):
        attrs = cast("dict[str, Any]", authz_fields())

    attrs["id"] = str(entity.pk)
    result = [Entity(ref, attrs=attrs)]

    # Transitively include any entities the model declares as related so Cedar
    # can resolve `resource.foo.bar` attribute chains. Models opt in by
    # defining `authz_related_entities()` → iterable of related Django models.
    # ``seen`` guards against cycles (A → B → A) that would otherwise recurse
    # unboundedly.
    related_fn = getattr(entity, "authz_related_entities", None)
    if callable(related_fn):
        for related in cast("Iterable[Any]", related_fn() or ()):
            result.extend(_make_entities(related, principal_attribute_providers, seen))

    return result


def _merge_entities(entities: Iterable[Entity]) -> list[Entity]:
    """Combine entities that arrive more than once under the same EntityRef.

    Attributes are merged recursively through records and parents are
    unioned. On a genuine conflict (the same attribute with different values)
    the first value wins and a warning names the entity type and attribute.
    Entities arrive in this order: provider-built ``Entity`` objects, the
    principal and its groups, the principal's related models, then the
    resource walk.
    """
    merged: dict[EntityRef, Entity] = {}
    for entity in entities:
        existing = merged.get(entity.ref)
        if existing is None:
            merged[entity.ref] = entity
            continue
        merged[entity.ref] = Entity(
            entity.ref,
            attrs=_merge_attrs(existing.attrs, entity.attrs, entity.ref.type, ""),
            parents=set(existing.parents) | set(entity.parents),
        )
    return list(merged.values())


def _is_record(value: Any) -> bool:
    # Entity references and extension values are single Cedar values, not
    # records to merge key by key.
    return (
        isinstance(value, Mapping) and "__entity" not in value and "__extn" not in value
    )


def _merge_attrs(
    first: Mapping[str, Any], second: Mapping[str, Any], entity_type: str, prefix: str
) -> dict[str, Any]:
    result = dict(first)
    for key, value in second.items():
        if key not in result:
            result[key] = value
        elif _is_record(result[key]) and _is_record(value):
            result[key] = _merge_attrs(
                result[key], value, entity_type, f"{prefix}{key}."
            )
        elif result[key] != value:
            logger.warning(
                "Conflicting values for attribute %s%s of a %s entity from "
                "different sources; keeping the first",
                prefix,
                key,
                entity_type,
            )
    return result


def _deep_merge(dst: dict[str, Any], src: Mapping[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, Mapping) and isinstance(dst.get(k), Mapping):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst
