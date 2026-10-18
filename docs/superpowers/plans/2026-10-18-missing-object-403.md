# Missing Objects Answer 403 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a missing object in `get_resource()` indistinguishable from a Cedar denial (both 403), and fetch the object once per request instead of twice.

**Architecture:** Two self-contained edits to `src/django_cedar/views.py`. `CedarAuthorizationMixin.authorize_request()` wraps its `get_resource()` call and converts `Http404`/`ObjectDoesNotExist` into `PermissionDenied`. `ResourceIsCurrentObjectMixin` gains a memoising `get_object()` so Django's handlers reuse the instance Cedar authorized.

**Tech Stack:** Python 3.12+, Django 5.2/6.0, pytest + pytest-django, ruff, pyright, uv.

**Spec:** `docs/superpowers/specs/2026-10-18-missing-object-403-design.md`

## Global Constraints

- All commands run via `uv run` from `/Users/acaine/src/django-cedar`.
- Import style: one `from x import y` per line (ruff isort `force-single-line`).
- `uv run ruff check`, `uv run ruff format --check` and `uv run pyright` must pass before every commit (pre-commit runs ruff automatically).
- Typing idiom: targeted `Any`/`cast` at Django boundaries; no django-stubs, no `type: ignore` beyond those already present.
- The converted exception is exactly `PermissionDenied("Forbidden")` — the same class and message `Authz.authorize()` raises.
- Only `django.http.Http404` and `django.core.exceptions.ObjectDoesNotExist` are converted. Nothing else.
- The conversion must raise; never fall back to `resource = None`.
- CHANGELOG entries go under `## [Unreleased]`; the version bump to 0.3.0 is done at release time with `make bump PART=minor`, not in this plan.
- Commits are GPG-signed by the repo-local git config — do not change git config. End every commit message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Tests use the existing idiom in `tests/test_views.py`: `@patch("django_cedar.views.create_authz")`, `RequestFactory` via the `rf` fixture, `_make_mock_user()`, `_make_anon_user()`, `_dispatch(view_class, request, **kwargs)`. No database. `template_name = "test.html"` on view classes (responses are lazy `TemplateResponse`s and are never rendered).

## Review Focus

- **Anonymous principal, missing object:** a view without `LoginRequiredMixin` reached by an anonymous user for a nonexistent pk must answer 403, not 404 — pinned in Task 1.
- **HEAD on a missing object:** HEAD is authorized with the GET action, so it must convert the same way — pinned in Task 1.
- **`MultipleObjectsReturned` must stay loud:** it is not an `ObjectDoesNotExist` subclass and must propagate unchanged — pinned in Task 1 (parametrized with `AttributeError`).
- **Memo is per view instance, not per class:** a second view instance for a second request must query again; a class-level cache would serve request A's object to request B — pinned in Task 2.
- **Real Django lookup path for a missing row:** `SingleObjectMixin.get_object()` raising `Http404` from `queryset.get()` must come out as 403 end to end through both mixins — pinned in Task 2.

---

### Task 1: Convert "not found" to "forbidden" in `authorize_request()`

**Files:**
- Modify: `src/django_cedar/views.py` (imports at top; `CedarAuthorizationMixin.authorize_request`, lines ~57-93)
- Modify: `README.md:87` (denied-requests paragraph) and `README.md:104-112` (custom scoping example)
- Modify: `CHANGELOG.md` under `## [Unreleased]`
- Test: `tests/test_views.py` (new class `TestMissingResource`)

**Interfaces:**
- Consumes: existing `CedarAuthorizationMixin.get_resource(self, request) -> Any`.
- Produces: `authorize_request(self, request) -> None` now raises `PermissionDenied("Forbidden")` when `get_resource()` raises `Http404` or `ObjectDoesNotExist`, before `create_authz()` is called. Task 2 relies on this: its end-to-end test expects the conversion to already exist.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_views.py` imports: `from django.core.exceptions import MultipleObjectsReturned`, `from django.core.exceptions import ObjectDoesNotExist`, `from django.http import Http404`. Add a new class after `TestCedarAuthorizationMixin`:

```python
class TestMissingResource:
    @staticmethod
    def _view_raising(exc):
        class RaisingView(CedarAuthorizationMixin, TemplateView):
            action_names = {"GET": "ViewObj"}
            template_name = "test.html"

            def get_resource(self, request):
                raise exc

        return RaisingView

    @pytest.mark.parametrize(
        "exc", [Http404("gone"), ObjectDoesNotExist("gone")], ids=["http404", "doesnotexist"]
    )
    @patch("django_cedar.views.create_authz")
    def test_missing_resource_raises_permission_denied(self, mock_create_authz, rf, exc):
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
    def test_missing_resource_on_head_raises_permission_denied(self, mock_create_authz, rf):
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_views.py::TestMissingResource -v`
Expected: all six cases FAIL. The four `missing_resource` cases raise `Http404`/`ObjectDoesNotExist` instead of `PermissionDenied`; the two `other_errors` cases fail on `assert_not_called()` because `create_authz()` currently runs before `get_resource()`.

- [ ] **Step 3: Implement the conversion in `src/django_cedar/views.py`**

Add imports `from django.core.exceptions import ObjectDoesNotExist`, `from django.core.exceptions import PermissionDenied`, `from django.http import Http404`. In `authorize_request()`, replace `resource = self.get_resource(request)` with:

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

Also move `authz = create_authz()` from above the lookup to just after the `try`/`except`, so the Cedar engine is only constructed on the success path (the tests assert `create_authz` is never called on a miss). Nothing else in the method changes.

- [ ] **Step 4: Run the whole test suite and linters**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`
Expected: all tests PASS, no lint or type errors.

- [ ] **Step 5: Document the behaviour**

`README.md:87`: after "Denied requests raise `django.core.exceptions.PermissionDenied` (HTTP 403)." add a sentence: if `get_resource()` raises `django.http.Http404` or `django.core.exceptions.ObjectDoesNotExist`, the request is also answered with 403 rather than 404, so a denied principal cannot tell objects that exist from ones that don't. Misconfiguration errors (`AttributeError`, `MultipleObjectsReturned`) are not converted.

`README.md` custom-scoping example (line ~111): add a trailing comment on the `Project.objects.get(...)` line: `# missing project → 403, not 500`.

`CHANGELOG.md` under `## [Unreleased]`, new `### Security` section above `### Changed`:

```markdown
### Security

- A missing object in `get_resource()` (`Http404` or `ObjectDoesNotExist`)
  now raises `PermissionDenied` (403) instead of surfacing as 404 or 500,
  so a denied principal can no longer enumerate which objects exist.
  Projects relying on 404 for missing objects in `Authorized*` views
  should expect 403.
```

- [ ] **Step 6: Commit**

```bash
git add src/django_cedar/views.py tests/test_views.py README.md CHANGELOG.md
git commit -m "fix: answer 403 for missing objects in get_resource()

A denied principal could distinguish objects that exist (403) from ones
that don't (404) and enumerate ids. Http404 and ObjectDoesNotExist raised
by get_resource() now become PermissionDenied before Cedar is consulted.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Memoise `get_object()` in `ResourceIsCurrentObjectMixin`

**Files:**
- Modify: `src/django_cedar/views.py` (`ResourceIsCurrentObjectMixin`, lines ~100-109)
- Modify: `README.md:98` (mixin bullet)
- Modify: `CHANGELOG.md` under `## [Unreleased]` → `### Changed`
- Test: `tests/test_views.py` (`TestResourceIsCurrentObjectMixin`)

**Interfaces:**
- Consumes: Task 1's conversion in `authorize_request()`; Django's `SingleObjectMixin.get_object(self, queryset=None)`.
- Produces: `ResourceIsCurrentObjectMixin.get_object(self, queryset: Any = None) -> Any` (memoised for `queryset is None`); `get_resource(self, request) -> Any` unchanged in signature and still sets `self.object`.

- [ ] **Step 1: Write the failing tests**

Add a module-level helper and four tests to `tests/test_views.py`. Add `from django.views.generic import DetailView` to the imports.

```python
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


class _DetailWithQueryset(ResourceIsCurrentObjectMixin, CedarAuthorizationMixin, DetailView):
    action_names = {"GET": "ViewObj"}
    template_name = "test.html"
    mock_queryset: Any = None

    def get_queryset(self):
        return self.mock_queryset
```

In `TestResourceIsCurrentObjectMixin`:

```python
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
    def test_missing_row_raises_permission_denied_end_to_end(self, mock_create_authz, rf):
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_views.py::TestResourceIsCurrentObjectMixin -v`
Expected: `test_get_object_is_called_once_per_request` FAILS (`get` called twice); `test_memo_is_per_instance` FAILS (`get` called 3 times); `test_missing_row_raises_permission_denied_end_to_end` and `test_explicit_queryset_bypasses_memo` PASS already (they pin behaviour the change must keep).

- [ ] **Step 3: Implement the memo in `src/django_cedar/views.py`**

Add a module-level sentinel `_UNSET = object()`. Replace the mixin body with:

```python
class ResourceIsCurrentObjectMixin:
    """..."""  # keep docstring; add a line: get_object() is called once per request.

    _cedar_object: Any = _UNSET

    def get_object(self, queryset: Any = None) -> Any:
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

- [ ] **Step 4: Run the whole test suite and linters**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`
Expected: all tests PASS, no lint or type errors.

- [ ] **Step 5: Document the behaviour**

`README.md:98`: change the bullet to "`ResourceIsCurrentObjectMixin` — authorize against `self.get_object()`; the object is fetched once per request and reused by the view's handler."

`CHANGELOG.md` under `## [Unreleased]` → `### Changed`, add:

```markdown
- `ResourceIsCurrentObjectMixin` memoises `get_object()` so the object is
  fetched once per request instead of twice (once for authorization, once
  by the Django handler).
```

- [ ] **Step 6: Commit**

```bash
git add src/django_cedar/views.py tests/test_views.py README.md CHANGELOG.md
git commit -m "perf: fetch the object once per request in ResourceIsCurrentObjectMixin

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
