# django-cedar 0.3.0: missing objects answer 403 — Design

**Date:** 2026-10-18
**Status:** Draft for review

## Purpose

Close an object-existence oracle in the view layer. Today a request to an
authorized detail/update/delete view yields three distinguishable answers:
200 (exists, permitted), 403 (exists, Cedar denied), 404 (does not exist).
A principal who is denied on everything can therefore walk primary keys
and learn exactly which objects exist. After this change a missing object
is indistinguishable from a denied one: both raise
`django.core.exceptions.PermissionDenied` and render the project's 403
response.

While in the same code, remove the duplicate `get_object()` call that the
object-resource mixin currently causes on every request.

## Decisions

| Topic | Decision |
|---|---|
| Collapse direction | Missing → 403, not forbidden → 404. Matches the library's documented contract ("denied requests raise `PermissionDenied`"), keeps "you lack access" visible to legitimate users. RFC 9110 blesses the opposite collapse; both close the oracle. |
| Where the conversion lives | `CedarAuthorizationMixin.authorize_request()`, around the `self.get_resource(request)` call — not in `ResourceIsCurrentObjectMixin`. This also covers custom `get_resource()` overrides (including the README's `Project.objects.get(...)` example, which today produces a 500) and the async dispatch path for free. |
| Exceptions converted | `django.http.Http404` and `django.core.exceptions.ObjectDoesNotExist` only. `AttributeError` (no pk/slug in URLconf) and `MultipleObjectsReturned` are misconfiguration and stay loud. |
| Opt-out hook | None (YAGNI). This is a security default; a project that wants 404 can override `authorize_request()`. |
| Admin special-casing | None. Cedar needs the resource to decide anything, so there is no principal for whom a missing object can safely be reported as 404. |
| Duplicate `get_object()` | Collapsed by memoising in `ResourceIsCurrentObjectMixin.get_object()` for the default (`queryset=None`) call. |
| Version | 0.3.0 (SemVer minor, pre-1.0): observable behaviour change (404 → 403) for consumers. |

## Changes (`src/django_cedar/views.py`)

### 1. Convert "not found" to "forbidden" during authorization

In `CedarAuthorizationMixin.authorize_request()`:

```python
try:
    resource = self.get_resource(request)
except (Http404, ObjectDoesNotExist) as exc:
    logger.info(
        f"Authz denied: resource not found for action '{action}' "
        f"(user '{request.user}'): {exc}"
    )
    raise PermissionDenied("Forbidden") from exc
```

- The raised exception is the same class and message Cedar denials use
  (`PermissionDenied("Forbidden")`), so the response goes through the same
  handler and template. Nothing in the response body distinguishes the two.
- The server-side log line *does* distinguish them so operators can tell a
  real denial from a stale link. That is not visible to the client.
- The conversion must raise. It must never fall back to `resource = None`
  (`System::"global"`): a type-wide permit policy would then succeed for a
  nonexistent id, which is worse than the oracle being fixed.
- Only the `get_resource()` call is wrapped. `authz.authorize()` and the
  `OPTIONS`/no-action early returns are untouched.
- Because `_cedar_async_dispatch` calls the same `authorize_request()` via
  `sync_to_async`, the async path gets the behaviour without further work.

Residual: the denied path runs Cedar and the missing path does not, so a
timing difference exists. It is small and not practically exploitable over
a network; explicitly not addressed.

### 2. Memoise `get_object()` in `ResourceIsCurrentObjectMixin`

Today `get_resource()` calls `get_object()` during `dispatch()`, and then
Django's `BaseDetailView.get`, `BaseUpdateView.get/post`,
`BaseDeleteView.post` and `DeletionMixin.delete` each call
`self.object = self.get_object()` again — two identical queries per request.

New shape:

```python
_UNSET = object()

class ResourceIsCurrentObjectMixin:
    _cedar_object: Any = _UNSET

    def get_object(self, queryset=None):
        if queryset is None and self._cedar_object is not _UNSET:
            return self._cedar_object
        obj = cast(Any, super()).get_object(queryset)
        if queryset is None:
            self._cedar_object = obj
        return obj

    def get_resource(self, request) -> Any:
        self.object = self.get_object()
        return self.object
```

- Memoisation is per view instance. Django's `as_view()` instantiates a
  fresh view per request, so the cache never crosses requests.
- Only the default call (`queryset is None`) is memoised; an explicit
  queryset (as `DateDetailView` passes) always hits the database.
- A subclass that defines its own `get_object()` sits earlier in the MRO
  and bypasses the memo, exactly as today. No behaviour change for it.
- The instance Cedar authorized is now the same instance the handler acts
  on (update/delete), removing a small check-then-act window between two
  fetches.
- `get_resource()` still sets `self.object` (existing test
  `test_sets_self_object` relies on it).

`cast(Any, super())` follows the project's pyright idiom (no django-stubs,
no `type: ignore`).

## Testing (`tests/test_views.py`)

All with the existing `@patch("django_cedar.views.create_authz")` +
`RequestFactory` + `_dispatch()` idiom; no database needed.

In `TestCedarAuthorizationMixin` (or a new `TestMissingResource` class):

1. `get_resource()` raises `Http404` → `_dispatch` raises
   `PermissionDenied`, and `mock_authz.authorize` was **not called**
   (guards against the `None`-fallback bug).
2. `get_resource()` raises a model `DoesNotExist` (any
   `ObjectDoesNotExist` subclass) → same assertions.
3. `get_resource()` raises `AttributeError` → propagates unchanged
   (misconfiguration stays loud). One such negative test is enough.
4. A view whose `action_names` has no entry for the method (and no
   handler, so no `ImproperlyConfigured`) never calls `get_resource()`;
   this already holds, no new test required.

In `TestResourceIsCurrentObjectMixin`:

5. Through a real `DetailView` subclass whose `get_queryset()` returns a
   `MagicMock` queryset (so `SingleObjectMixin.get_object()` runs for real
   and the mixin's memo is exercised), a GET with `pk` in kwargs calls
   `queryset.get()` exactly once and the handler's `self.object` is the
   same instance Cedar was authorized against.
6. Same arrangement with `queryset.get.side_effect = Http404(...)` →
   `PermissionDenied` raised, `authorize` not called (end-to-end through
   the real mixin, not a stubbed `get_resource`).
7. `get_object(queryset=explicit_qs)` bypasses the memo: called twice,
   `explicit_qs.get()` is invoked twice.

No async-specific test is required: the conversion lives in the shared
`authorize_request()`.

## Documentation

- README, under "Denied requests raise `PermissionDenied` (HTTP 403)":
  add that if `get_resource()` raises `Http404` or `ObjectDoesNotExist`
  the request is also answered with 403, so that a denied principal cannot
  distinguish objects that exist from ones that don't. Note that
  misconfiguration errors are not converted.
- README custom-scoping example (`Project.objects.get(...)`): add a one-line
  comment that a missing project yields 403, not 500.
- README mixin table/description for `ResourceIsCurrentObjectMixin`: note
  `get_object()` is called once per request.
- CHANGELOG `[Unreleased]` → becomes 0.3.0 at release:
  - **Security**: "A missing object in `get_resource()` (`Http404` or
    `ObjectDoesNotExist`) now raises `PermissionDenied` (403) instead of
    404/500, so a denied principal can no longer enumerate which objects
    exist. Projects relying on 404 for missing objects in `Authorized*`
    views should expect 403."
  - **Changed**: "`ResourceIsCurrentObjectMixin` memoises `get_object()`
    so the object is fetched once per request instead of twice."

## Out of scope

- Making the 403/404 choice configurable.
- Timing-channel mitigation.
- Any change to `CurrentUserScopedMixin` (its queryset filter already
  yields a uniform 404 for "missing" and "not mine"; left as is).
- Changing `Authz.authorize()` or Cedar entity construction.
- app-studio: it consumes `django-cedar` from PyPI (locked at 0.1.0), so
  it picks this up by bumping the dependency after 0.3.0 is released. That
  bump also pulls in 0.2.0's principal-naming change and is a separate
  task.
