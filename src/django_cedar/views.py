from __future__ import annotations

import logging
from typing import Any
from typing import cast

from asgiref.sync import sync_to_async
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured
from django.views.generic import CreateView
from django.views.generic import DeleteView
from django.views.generic import DetailView
from django.views.generic import FormView
from django.views.generic import ListView
from django.views.generic import TemplateView
from django.views.generic import UpdateView

from django_cedar.authz import create_authz

logger = logging.getLogger(__name__)


class CedarAuthorizationMixin:
    """
    Mixin that performs Cedar authorization on every request via dispatch().

    Subclasses must define ``action_names`` mapping HTTP methods to Cedar action
    strings.  Override ``get_resource`` to control the Cedar resource used for
    the authorization check (defaults to ``None`` → ``System::"global"``).

    Usage::

        class MyView(LoginRequiredMixin, CedarAuthorizationMixin, DetailView):
            action_names = {"GET": "ViewWidget"}
            model = Widget

    Async views: ``authorize_request`` calls into the ORM (group membership,
    ``get_resource`` may load a parent object). For async views we hop into
    a sync thread via ``sync_to_async`` so those queries don't trip
    ``SynchronousOnlyOperation``.
    """

    action_names: dict[str, str] = {}

    def dispatch(self, request, *args, **kwargs) -> Any:  # type: ignore[override]
        if self.view_is_async:  # type: ignore[attr-defined]
            return self._cedar_async_dispatch(request, *args, **kwargs)
        self.authorize_request(request)
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]

    async def _cedar_async_dispatch(self, request, *args, **kwargs):
        # Unique method name (rather than ``_adispatch``) so multiple
        # dispatch-overriding mixins in the same MRO don't shadow each
        # other — ``self._adispatch`` would always resolve to the first
        # one and recurse.
        await sync_to_async(self.authorize_request, thread_sensitive=True)(request)
        return await super().dispatch(request, *args, **kwargs)  # type: ignore[misc]

    def authorize_request(self, request) -> None:
        method = request.method.upper()
        if method == "OPTIONS":
            return
        # Django's View.setup() aliases head=get, so a HEAD request executes
        # the full GET code path. Authorize it with the GET action rather than
        # letting it bypass authorization.
        if method == "HEAD":
            method = "GET"
        action = self.action_names.get(method)
        if action is None:
            if hasattr(self, method.lower()):
                raise ImproperlyConfigured(
                    f"{type(self).__name__} has a {method.lower()}() handler but no "
                    f"action_names entry for '{method}'. Add "
                    f"action_names['{method}'] to enable Cedar authorization "
                    f"for this method."
                )
            return
        authz = create_authz()
        resource = self.get_resource(request)
        logger.debug(
            f"Authorizing action '{action}' on resource '{resource}' "
            f"for user '{request.user}'"
        )
        authz.authorize(request.user, action, resource)

    def get_resource(self, request) -> Any:
        """Return the Cedar resource for this request.

        Default is ``None``, which maps to ``System::"global"`` in Cedar.
        """
        return None


class ResourceIsCurrentObjectMixin:
    """Use ``self.get_object()`` as the Cedar resource.

    For detail/update/delete views where the resource being authorized is the
    object being acted on.
    """

    def get_resource(self, request) -> Any:
        self.object = cast(Any, self).get_object()
        return self.object


class CurrentUserScopedMixin:
    """Use the current user as the Cedar resource and filter the queryset to
    objects belonging to that user."""

    def get_resource(self, request) -> Any:
        return request.user

    def get_queryset(self):
        qs = cast(Any, super()).get_queryset()
        request: Any = cast(Any, self).request
        if not request.user or not request.user.is_authenticated:
            return qs.none()
        return qs.filter(user=request.user)


class AuthorizedDetailView(
    ResourceIsCurrentObjectMixin, CedarAuthorizationMixin, DetailView
):
    pass


class AuthorizedListView(CedarAuthorizationMixin, ListView):
    pass


class AuthorizedCreateView(CedarAuthorizationMixin, CreateView):
    pass


class AuthorizedUpdateView(
    ResourceIsCurrentObjectMixin, CedarAuthorizationMixin, UpdateView
):
    pass


class AuthorizedDeleteView(
    ResourceIsCurrentObjectMixin, CedarAuthorizationMixin, DeleteView
):
    pass


class AuthorizedTemplateView(CedarAuthorizationMixin, TemplateView):
    pass


class AuthorizedFormView(CedarAuthorizationMixin, FormView):
    pass


class AsyncLoginRequiredMixin(LoginRequiredMixin):
    """LoginRequiredMixin that works on async views.

    Django's stock ``LoginRequiredMixin.dispatch`` reads
    ``request.user.is_authenticated`` synchronously; on an async view that
    triggers a sync ORM lookup through ``SimpleLazyObject`` and
    ``SynchronousOnlyOperation`` is raised. We resolve the user via the
    async helper ``request.auser()`` first, then populate
    ``request._cached_user`` so any later sync access (LoginRequiredMixin's
    own check, downstream mixins) sees the cached value and skips the
    lookup entirely.
    """

    def dispatch(self, request, *args, **kwargs) -> Any:  # type: ignore[override]
        if self.view_is_async:  # type: ignore[attr-defined]
            return self._login_async_dispatch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    async def _login_async_dispatch(self, request, *args, **kwargs):
        # Unique method name (rather than the generic ``_adispatch``) so
        # we don't shadow ``CedarAuthorizationMixin``'s async helper when
        # both mixins land in the same view's MRO.
        user = await request.auser()
        request._cached_user = user
        if not user.is_authenticated:
            return self.handle_no_permission()
        return await cast(Any, super(LoginRequiredMixin, self)).dispatch(
            request, *args, **kwargs
        )
