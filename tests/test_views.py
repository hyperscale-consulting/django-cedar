from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.views.generic import ListView
from django.views.generic import TemplateView

from django_cedar.views import CedarAuthorizationMixin
from django_cedar.views import CurrentUserScopedMixin
from django_cedar.views import ResourceIsCurrentObjectMixin

PERMIT_ALL = "permit(principal, action, resource);"
DENY_ALL = "forbid(principal, action, resource);"


@pytest.fixture
def rf():
    return RequestFactory()


def _make_mock_user(pk=1):
    user = MagicMock()
    user.pk = pk
    user.is_authenticated = True
    user.is_staff = False
    user.is_superuser = False
    user.groups.all.return_value = []
    return user


def _make_anon_user():
    user = MagicMock()
    user.pk = None
    user.is_authenticated = False
    return user


def _dispatch(view_class, request, **kwargs):
    """Simulate Django's as_view() lifecycle: instantiate, setup, dispatch."""
    view = view_class()
    view.setup(request, **kwargs)
    return view.dispatch(request, **kwargs)


class SimpleAuthorizedView(CedarAuthorizationMixin, TemplateView):
    action_names = {"GET": "ViewPage"}
    template_name = "test.html"


class TestCedarAuthorizationMixin:
    @patch("django_cedar.views.create_authz")
    def test_authorized_request_succeeds(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        request = rf.get("/")
        request.user = _make_mock_user()
        _dispatch(SimpleAuthorizedView, request)

        mock_authz.authorize.assert_called_once_with(request.user, "ViewPage", None)

    @patch("django_cedar.views.create_authz")
    def test_denied_request_raises_permission_denied(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_authz.authorize.side_effect = PermissionDenied("Forbidden")
        mock_create_authz.return_value = mock_authz

        request = rf.get("/")
        request.user = _make_mock_user()
        with pytest.raises(PermissionDenied):
            _dispatch(SimpleAuthorizedView, request)

    @patch("django_cedar.views.create_authz")
    def test_options_bypasses_authorization(self, mock_create_authz, rf):
        request = rf.options("/")
        request.user = _make_mock_user()
        _dispatch(SimpleAuthorizedView, request)
        mock_create_authz.assert_not_called()

    @patch("django_cedar.views.create_authz")
    def test_head_bypasses_authorization(self, mock_create_authz, rf):
        request = rf.head("/")
        request.user = _make_mock_user()
        _dispatch(SimpleAuthorizedView, request)
        mock_create_authz.assert_not_called()

    @patch("django_cedar.views.create_authz")
    def test_unmapped_method_without_handler_skips_auth_returns_405(
        self, mock_create_authz, rf
    ):
        request = rf.post("/")
        request.user = _make_mock_user()
        response = _dispatch(SimpleAuthorizedView, request)
        assert response.status_code == 405
        mock_create_authz.assert_not_called()

    def test_unmapped_method_with_handler_raises_improperly_configured(self, rf):
        class BadView(CedarAuthorizationMixin, TemplateView):
            action_names = {"GET": "ViewPage"}
            template_name = "test.html"

            def post(self, request, *args, **kwargs):
                return self.get(request, *args, **kwargs)

        request = rf.post("/")
        request.user = _make_mock_user()
        with pytest.raises(ImproperlyConfigured, match="post.*handler.*action_names"):
            _dispatch(BadView, request)

    @patch("django_cedar.views.create_authz")
    def test_anonymous_user_still_authorized(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        request = rf.get("/")
        request.user = _make_anon_user()
        _dispatch(SimpleAuthorizedView, request)

        mock_authz.authorize.assert_called_once_with(request.user, "ViewPage", None)

    @patch("django_cedar.views.create_authz")
    def test_get_resource_called_with_request(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        sentinel = object()

        class CustomResourceView(CedarAuthorizationMixin, TemplateView):
            action_names = {"GET": "ViewThing"}
            template_name = "test.html"

            def get_resource(self, request):
                return sentinel

        request = rf.get("/")
        request.user = _make_mock_user()
        _dispatch(CustomResourceView, request)

        mock_authz.authorize.assert_called_once_with(
            request.user, "ViewThing", sentinel
        )

    @patch("django_cedar.views.create_authz")
    def test_multiple_action_names(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        class MultiMethodView(CedarAuthorizationMixin, TemplateView):
            action_names = {"GET": "ViewPage", "POST": "UpdatePage"}
            template_name = "test.html"

            def post(self, request, *args, **kwargs):
                return self.get(request, *args, **kwargs)

        request = rf.post("/")
        request.user = _make_mock_user()
        _dispatch(MultiMethodView, request)

        mock_authz.authorize.assert_called_once_with(request.user, "UpdatePage", None)


class TestResourceIsCurrentObjectMixin:
    @patch("django_cedar.views.create_authz")
    def test_get_resource_returns_object(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        mock_obj = MagicMock()

        class ObjView(
            ResourceIsCurrentObjectMixin, CedarAuthorizationMixin, TemplateView
        ):
            action_names = {"GET": "ViewObj"}
            template_name = "test.html"

            def get_object(self, queryset=None):
                return mock_obj

        request = rf.get("/")
        request.user = _make_mock_user()
        _dispatch(ObjView, request)

        mock_authz.authorize.assert_called_once_with(request.user, "ViewObj", mock_obj)

    @patch("django_cedar.views.create_authz")
    def test_sets_self_object(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        mock_obj = MagicMock()
        captured_view = {}

        class ObjView(
            ResourceIsCurrentObjectMixin, CedarAuthorizationMixin, TemplateView
        ):
            action_names = {"GET": "ViewObj"}
            template_name = "test.html"

            def get_object(self, queryset=None):
                return mock_obj

            def get(self, request, *args, **kwargs):
                captured_view["object"] = self.object
                return super().get(request, *args, **kwargs)

        request = rf.get("/")
        request.user = _make_mock_user()
        _dispatch(ObjView, request)

        assert captured_view["object"] is mock_obj


class TestCurrentUserScopedMixin:
    @patch("django_cedar.views.create_authz")
    def test_get_resource_returns_user(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        class UserScopedView(
            CurrentUserScopedMixin, CedarAuthorizationMixin, TemplateView
        ):
            action_names = {"GET": "ViewStuff"}
            template_name = "test.html"

        request = rf.get("/")
        user = _make_mock_user()
        request.user = user
        _dispatch(UserScopedView, request)

        mock_authz.authorize.assert_called_once_with(user, "ViewStuff", user)

    def test_get_queryset_filters_by_user(self):
        mock_qs = MagicMock()
        user = _make_mock_user(pk=5)
        mock_qs.filter.return_value = mock_qs

        class ConcreteScoped(CurrentUserScopedMixin, ListView):
            model = None

        view = ConcreteScoped()
        view.request = MagicMock()
        view.request.user = user
        view.queryset = mock_qs

        view.get_queryset()
        mock_qs.filter.assert_called_once_with(user=user)

    def test_get_queryset_returns_none_for_anon(self):
        mock_qs = MagicMock()
        mock_qs.none.return_value = MagicMock()

        class ConcreteScoped(CurrentUserScopedMixin, ListView):
            model = None

        view = ConcreteScoped()
        view.request = MagicMock()
        view.request.user = _make_anon_user()
        view.queryset = mock_qs

        result = view.get_queryset()
        mock_qs.none.assert_called_once()
        assert result is mock_qs.none.return_value
