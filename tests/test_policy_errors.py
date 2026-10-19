"""Policies that error during evaluation are logged, and skipped forbids raise."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import override_settings

from django_cedar.authz import Authz
from django_cedar.authz import entity_ref
from django_cedar.authz import ForbidPolicyError

PERMIT_ALL = "permit(principal, action, resource);"


def _make_mock_user(pk: Any = 1):
    user = MagicMock()
    user.pk = pk
    user.is_authenticated = True
    user.is_staff = False
    user.is_superuser = False
    user.groups.all.return_value = []
    return user


class Node:
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


Report: Any = type("Report", (Node,), {})
Period = type("Period", (Node,), {})
Organisation = type("Organisation", (Node,), {})


def _broken_chain() -> Any:
    """Report -> Period -> Organisation, but Period doesn't declare its hop."""
    org = Organisation("org-secret-pk", status="suspended")
    period = Period("period-secret-pk", nxt=org, declare=False)
    return Report("report-secret-pk", nxt=period)


MISSING_LINK_FORBID = (
    PERMIT_ALL
    + """
@id("suspended-orgs")
forbid(principal, action, resource)
when { resource.nxt.nxt.status == "suspended" };
"""
)


class TestStrictMode:
    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=True)
    def test_missing_link_forbid_raises(self):
        authz = Authz(policies=MISSING_LINK_FORBID)
        with pytest.raises(ForbidPolicyError) as exc:
            authz.authorize(_make_mock_user(), "View", _broken_chain())
        assert "policy1" in str(exc.value)
        assert "suspended-orgs" in str(exc.value)
        assert "secret" not in str(exc.value)

    def test_forbid_error_is_not_permission_denied(self):
        # A PermissionDenied subclass would render as an ordinary 403 and pass
        # tests that expect a denial; it must surface as its own error.
        assert not issubclass(ForbidPolicyError, PermissionDenied)

    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=True)
    def test_raises_even_when_another_policy_denies(self):
        policy = MISSING_LINK_FORBID + "forbid(principal, action, resource);"
        with pytest.raises(ForbidPolicyError):
            Authz(policies=policy).authorize(_make_mock_user(), "View", _broken_chain())

    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=True)
    def test_permit_errors_do_not_raise(self, caplog):
        policy = (
            "permit(principal, action, resource) "
            'when { resource.nxt.nxt.status == "active" };'
        )
        with caplog.at_level(logging.ERROR, logger="django_cedar.authz"):
            with pytest.raises(PermissionDenied):
                Authz(policies=policy).authorize(
                    _make_mock_user(), "View", _broken_chain()
                )
        assert "policy0" in caplog.text

    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=True)
    def test_fixed_chain_does_not_raise(self):
        chain = _broken_chain()
        chain.nxt.declare = True
        with pytest.raises(PermissionDenied):  # the forbid now applies
            Authz(policies=MISSING_LINK_FORBID).authorize(
                _make_mock_user(), "View", chain
            )

    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=False)
    def test_constructor_argument_overrides_setting(self):
        authz = Authz(policies=MISSING_LINK_FORBID, raise_on_forbid_error=True)
        with pytest.raises(ForbidPolicyError):
            authz.authorize(_make_mock_user(), "View", _broken_chain())

    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=True)
    def test_unattributable_error_is_treated_as_forbid(self):
        result = MagicMock()
        result.allowed = True
        result.diagnostics.errors = ["something cedarpy has never said before"]
        with patch("django_cedar.authz.is_authorized", return_value=result):
            with pytest.raises(ForbidPolicyError):
                Authz(policies=PERMIT_ALL).authorize(_make_mock_user(), "View", None)


class TestNonStrictMode:
    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=False)
    def test_missing_link_forbid_allows_but_logs(self, caplog):
        # Cedar semantics: the errored forbid is skipped and the permit wins.
        with caplog.at_level(logging.ERROR, logger="django_cedar.authz"):
            Authz(policies=MISSING_LINK_FORBID).authorize(
                _make_mock_user(pk="user-secret-pk"), "View", _broken_chain()
            )
        [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
        message = record.getMessage()
        assert "policy1" in message
        assert "suspended-orgs" in message
        assert "forbid" in message
        assert "secret" not in message

    @override_settings(CEDAR_RAISE_ON_FORBID_ERROR=False)
    def test_attribute_error_reason_is_redacted(self, caplog):
        policy = (
            PERMIT_ALL
            + "forbid(principal, action, resource) when { resource.missing };"
        )
        with caplog.at_level(logging.ERROR, logger="django_cedar.authz"):
            Authz(policies=policy).authorize(
                _make_mock_user(), "View", Report("report-secret-pk")
            )
        assert "missing" in caplog.text  # the attribute name helps debugging
        assert "report-secret-pk" not in caplog.text

    def test_no_errors_no_logs(self, caplog):
        with caplog.at_level(logging.ERROR, logger="django_cedar.authz"):
            Authz(policies=PERMIT_ALL).authorize(_make_mock_user(), "View", None)
        assert not caplog.records


class TestStrictDefault:
    def test_on_under_debug(self, settings, monkeypatch):
        monkeypatch.delattr(mail, "outbox", raising=False)
        settings.DEBUG = True
        with pytest.raises(ForbidPolicyError):
            Authz(policies=MISSING_LINK_FORBID).authorize(
                _make_mock_user(), "View", _broken_chain()
            )

    def test_on_under_test_environment(self, settings):
        # pytest-django and Django's runner call setup_test_environment(),
        # which installs mail.outbox.
        settings.DEBUG = False
        assert hasattr(mail, "outbox")
        with pytest.raises(ForbidPolicyError):
            Authz(policies=MISSING_LINK_FORBID).authorize(
                _make_mock_user(), "View", _broken_chain()
            )

    def test_off_in_production(self, settings, monkeypatch):
        monkeypatch.delattr(mail, "outbox", raising=False)
        settings.DEBUG = False
        Authz(policies=MISSING_LINK_FORBID).authorize(
            _make_mock_user(), "View", _broken_chain()
        )
