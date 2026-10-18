from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import MultipleObjectsReturned
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.http import HttpResponse
from django.test import RequestFactory
from django.views.generic import DetailView
from django.views.generic import ListView
from django.views.generic import TemplateView
from django.views.generic import View

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
    def test_head_authorized_with_get_action(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        request = rf.head("/")
        request.user = _make_mock_user()
        _dispatch(SimpleAuthorizedView, request)

        mock_authz.authorize.assert_called_once_with(request.user, "ViewPage", None)

    @patch("django_cedar.views.create_authz")
    def test_head_without_get_handler_skips_auth(self, mock_create_authz, rf):
        # A view with no get handler has no GET action mapping and no get()
        # to alias HEAD onto: HEAD stays a no-op (Django returns 405).
        class PostOnlyView(CedarAuthorizationMixin, View):
            action_names = {"POST": "UpdatePage"}

            def post(self, request, *args, **kwargs):
                return HttpResponse(b"ok")

        request = rf.head("/")
        request.user = _make_mock_user()
        response = _dispatch(PostOnlyView, request)
        assert response.status_code == 405
        mock_create_authz.assert_not_called()

    def test_head_with_custom_head_handler_no_get_raises_improperly_configured(
        self, rf
    ):
        # A view with a custom head() but no get() must not silently skip
        # authorization: the fail-closed guard has to check for a *head*
        # handler (the original request method), not a get handler (the
        # translated action_names lookup method).
        class HeadOnlyView(CedarAuthorizationMixin, View):
            action_names: dict[str, str] = {}

            def head(self, request, *args, **kwargs):
                return HttpResponse(b"ok")

        request = rf.head("/")
        request.user = _make_mock_user()
        with pytest.raises(ImproperlyConfigured, match="head.*handler.*action_names"):
            _dispatch(HeadOnlyView, request)

    @patch("django_cedar.views.create_authz")
    def test_head_with_custom_head_handler_get_action_mapped(
        self, mock_create_authz, rf
    ):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz

        class HeadOnlyView(CedarAuthorizationMixin, View):
            action_names = {"GET": "ViewPage"}

            def head(self, request, *args, **kwargs):
                return HttpResponse(b"ok")

        request = rf.head("/")
        request.user = _make_mock_user()
        _dispatch(HeadOnlyView, request)

        mock_authz.authorize.assert_called_once_with(request.user, "ViewPage", None)

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


class TestMissingResource:
    @staticmethod
    def _view_raising(exc, **attrs):
        class RaisingView(CedarAuthorizationMixin, TemplateView):
            action_names = {"GET": "ViewObj"}
            template_name = "test.html"

            def get_resource(self, request):
                raise exc

        for name, value in attrs.items():
            setattr(RaisingView, name, value)
        return RaisingView

    @pytest.mark.parametrize(
        "exc",
        [Http404("gone"), ObjectDoesNotExist("gone")],
        ids=["http404", "doesnotexist"],
    )
    @patch("django_cedar.views.create_authz")
    def test_missing_resource_raises_permission_denied(
        self, mock_create_authz, rf, exc
    ):
        request = rf.get("/")
        request.user = _make_mock_user()
        with pytest.raises(PermissionDenied):
            _dispatch(self._view_raising(exc), request)
        mock_create_authz.assert_not_called()

    @patch("django_cedar.views.create_authz")
    def test_missing_resource_for_anonymous_user_raises_permission_denied(
        self, mock_create_authz, rf
    ):
        request = rf.get("/")
        request.user = _make_anon_user()
        with pytest.raises(PermissionDenied):
            _dispatch(self._view_raising(Http404("gone")), request)
        mock_create_authz.assert_not_called()

    @patch("django_cedar.views.create_authz")
    def test_missing_resource_on_head_raises_permission_denied(
        self, mock_create_authz, rf
    ):
        request = rf.head("/")
        request.user = _make_mock_user()
        with pytest.raises(PermissionDenied):
            _dispatch(self._view_raising(Http404("gone")), request)
        mock_create_authz.assert_not_called()

    @pytest.mark.parametrize(
        "exc",
        [AttributeError("no pk or slug"), MultipleObjectsReturned("two")],
        ids=["attributeerror", "multipleobjectsreturned"],
    )
    @patch("django_cedar.views.create_authz")
    def test_other_errors_propagate_unchanged(self, mock_create_authz, rf, exc):
        request = rf.get("/")
        request.user = _make_mock_user()
        with pytest.raises(type(exc)):
            _dispatch(self._view_raising(exc), request)
        mock_create_authz.assert_not_called()

    @pytest.mark.parametrize(
        "exc",
        [Http404("gone"), ObjectDoesNotExist("gone")],
        ids=["http404", "doesnotexist"],
    )
    @patch("django_cedar.views.create_authz")
    def test_opt_out_lets_lookup_error_propagate(self, mock_create_authz, rf, exc):
        request = rf.get("/")
        request.user = _make_mock_user()
        view_class = self._view_raising(exc, deny_missing_resource=False)
        with pytest.raises(type(exc)):
            _dispatch(view_class, request)
        mock_create_authz.assert_not_called()


def _make_mock_queryset(obj=None, *, get_side_effect=None):
    """A queryset mock that SingleObjectMixin.get_object() can drive.

    Django's except clause evaluates ``queryset.model.DoesNotExist`` as an
    exception class, so it must be a real one, not a MagicMock attribute.
    """
    qs = MagicMock()
    qs.filter.return_value = qs
    qs.model.DoesNotExist = ObjectDoesNotExist
    qs.model._meta.verbose_name = "thing"
    if get_side_effect is not None:
        qs.get.side_effect = get_side_effect
    else:
        qs.get.return_value = obj
    return qs


class _DetailWithQueryset(
    ResourceIsCurrentObjectMixin, CedarAuthorizationMixin, DetailView
):
    action_names = {"GET": "ViewObj"}
    template_name = "test.html"
    mock_queryset: Any = None

    def get_queryset(self):
        return self.mock_queryset


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

    @patch("django_cedar.views.create_authz")
    def test_get_object_is_called_once_per_request(self, mock_create_authz, rf):
        mock_authz = MagicMock()
        mock_create_authz.return_value = mock_authz
        obj = MagicMock()
        captured = {}

        class V(_DetailWithQueryset):
            mock_queryset = _make_mock_queryset(obj)

            def get(self, request, *args, **kwargs):
                response = super().get(request, *args, **kwargs)
                captured["object"] = self.object
                return response

        request = rf.get("/")
        request.user = _make_mock_user()
        _dispatch(V, request, pk=1)

        V.mock_queryset.get.assert_called_once()
        assert captured["object"] is obj
        mock_authz.authorize.assert_called_once_with(request.user, "ViewObj", obj)

    @patch("django_cedar.views.create_authz")
    def test_missing_row_raises_permission_denied_end_to_end(
        self, mock_create_authz, rf
    ):
        class V(_DetailWithQueryset):
            mock_queryset = _make_mock_queryset(get_side_effect=ObjectDoesNotExist())

        request = rf.get("/")
        request.user = _make_mock_user()
        with pytest.raises(PermissionDenied):
            _dispatch(V, request, pk=1)
        mock_create_authz.assert_not_called()

    def test_explicit_queryset_bypasses_memo(self):
        view: Any = _DetailWithQueryset()
        view.kwargs = {"pk": 1}
        explicit = _make_mock_queryset(MagicMock())

        view.get_object(explicit)
        view.get_object(explicit)

        assert explicit.get.call_count == 2

    def test_memo_is_per_instance(self):
        qs = _make_mock_queryset(MagicMock())

        class V(_DetailWithQueryset):
            mock_queryset = qs

        first: Any = V()
        first.kwargs = {"pk": 1}
        second: Any = V()
        second.kwargs = {"pk": 1}

        first.get_object()
        first.get_object()
        second.get_object()

        assert qs.get.call_count == 2


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

        view: Any = ConcreteScoped()
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

        view: Any = ConcreteScoped()
        view.request = MagicMock()
        view.request.user = _make_anon_user()
        view.queryset = mock_qs

        result = view.get_queryset()
        mock_qs.none.assert_called_once()
        assert result is mock_qs.none.return_value
