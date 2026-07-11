from __future__ import annotations

from typing import Any

from cedarpy import format_policies
from django.conf import settings
from django.core.checks import CheckMessage
from django.core.checks import Error
from django.core.checks import register
from django.core.exceptions import ImproperlyConfigured

from django_cedar.authz import _resolve_policy_path
from django_cedar.authz import import_from_path

_PROVIDER_SETTINGS = (
    ("CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS", "get_attributes"),
    ("CEDAR_CONTEXT_PROVIDERS", "get_context"),
)


@register()
def check_cedar_config(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    errors: list[CheckMessage] = []
    errors.extend(_check_policy_file())
    errors.extend(_check_providers())
    return errors


def _check_policy_file() -> list[CheckMessage]:
    if not getattr(settings, "CEDAR_POLICY_PATH", None):
        return [
            Error(
                "The CEDAR_POLICY_PATH setting is not set.",
                hint="Set CEDAR_POLICY_PATH to the path of your Cedar policy "
                "file (relative paths resolve against BASE_DIR).",
                id="django_cedar.E001",
            )
        ]
    path = _resolve_policy_path()
    if not path.is_file():
        return [
            Error(
                f"Cedar policy file not found at {path}.",
                hint="Check the CEDAR_POLICY_PATH setting.",
                id="django_cedar.E002",
            )
        ]
    try:
        format_policies(path.read_text())
    except Exception as e:  # cedarpy raises on any parse failure
        return [
            Error(
                f"Cedar policy file at {path} failed to parse: {e}",
                id="django_cedar.E003",
            )
        ]
    return []


def _check_providers() -> list[CheckMessage]:
    errors: list[CheckMessage] = []
    for setting_name, required_method in _PROVIDER_SETTINGS:
        for dotted_path in getattr(settings, setting_name, []):
            try:
                provider_cls = import_from_path(dotted_path)
            except (ImportError, ImproperlyConfigured) as e:
                errors.append(
                    Error(
                        f"Could not import '{dotted_path}' from {setting_name}: {e}",
                        id="django_cedar.E004",
                    )
                )
                continue
            if not callable(getattr(provider_cls, required_method, None)):
                errors.append(
                    Error(
                        f"'{dotted_path}' in {setting_name} does not define a "
                        f"callable '{required_method}' method.",
                        id="django_cedar.E005",
                    )
                )
    return errors
