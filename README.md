# django-cedar

[Cedar](https://www.cedarpolicy.com/) policy-based authorization for Django.

Cedar is an open-source policy language for expressive, analyzable
permissions. django-cedar lets you express *who can do what* in Cedar policy
files instead of scattering permission logic through your views, and enforces
those policies with class-based-view mixins.

## Requirements

- Python 3.12+
- Django 5.2+

Any user model works, including custom `AUTH_USER_MODEL` classes. The Cedar
principal type is your user model's class name (e.g. `Member::"5"` for a
`Member` model; `User::"5"` with Django's default model). The `is_staff` and
`is_superuser` attributes and `Group` parent entities are included when your
model provides them — a bare `AbstractBaseUser` model gets just `id` plus any
provider-supplied attributes.

## Installation

```bash
pip install django-cedar
```

Add the app (optional, but recommended — it enables startup-time
configuration checks via Django's system check framework):

```python
INSTALLED_APPS = [
    # ...
    "django_cedar",
]
```

## Quickstart

**1. Write a policy file** (`policies.cedar` next to `manage.py`):

```cedar
// Staff can do anything
permit(principal, action, resource)
when { principal.is_staff };

// Anyone signed in can view widgets
permit(principal is User, action == Action::"ViewWidget", resource);
```

**2. Point Django at it:**

```python
CEDAR_POLICY_PATH = "policies.cedar"  # relative paths resolve against BASE_DIR
```

**3. Enforce it in your views:**

```python
from django_cedar.views import AuthorizedDetailView

from .models import Widget


class WidgetDetailView(AuthorizedDetailView):
    model = Widget
    action_names = {"GET": "ViewWidget"}
```

Every request is authorized in `dispatch()`. The Cedar request is built as:

- **principal** — `<UserModel>::"<pk>"` for authenticated users, where
  `<UserModel>` is your user model's class name via `get_user_model()`
  (`User::"<pk>"` with Django's default user model), or `Anonymous::"guest"`
  otherwise. The `id` attribute is always included; `is_staff` and
  `is_superuser` attributes and `Group::"<name>"` parent entities from your
  model's `groups` relation are included when your model provides them, so
  `principal in Group::"editors"` works out of the box for models that have
  one. A policy that references an attribute or entity the request doesn't
  supply errors, and Cedar skips it; for a `forbid` that means the request
  is *not* denied. See [When a policy errors](#when-a-policy-errors).
- **action** — `Action::"<name>"` from the view's `action_names` mapping
  (HTTP method → action name). HEAD requests are authorized using the view's
  `"GET"` action mapping; a `"HEAD"` key in `action_names` is not consulted.
- **resource** — the object returned by the view's `get_resource()` hook, as
  `<ModelClass>::"<pk>"`; `System::"global"` when there is no resource.

Denied requests raise `django.core.exceptions.PermissionDenied` (HTTP 403).
If `get_resource()` raises `django.http.Http404` or
`django.core.exceptions.ObjectDoesNotExist`, the request is also answered
with 403 rather than 404, so a denied principal cannot tell objects that
exist from ones that don't. Misconfiguration errors (`AttributeError`,
`MultipleObjectsReturned`) are not converted. To keep the old behaviour on a
particular view, set `deny_missing_resource = False` on it; the lookup
exception then propagates unchanged.

## Views and mixins

| Class | Resource used for the check |
|---|---|
| `AuthorizedDetailView` / `AuthorizedUpdateView` / `AuthorizedDeleteView` | `self.get_object()` |
| `AuthorizedListView` / `AuthorizedCreateView` / `AuthorizedTemplateView` / `AuthorizedFormView` | `System::"global"` (override `get_resource()`) |

Compose the behavior yourself with `CedarAuthorizationMixin` plus:

- `ResourceIsCurrentObjectMixin` — authorize against `self.get_object()`; the
  object is fetched once per request and reused by the view's handler.
- `CurrentUserScopedMixin` — authorize against the current user and filter
  the queryset to `user=<request.user>`.
- `AsyncLoginRequiredMixin` — a `LoginRequiredMixin` that works on async
  views. `CedarAuthorizationMixin` itself supports async views too.

Custom scoping is one method:

```python
class ProjectScopedView(CedarAuthorizationMixin, ListView):
    action_names = {"GET": "ListTasks"}

    def get_resource(self, request):
        return Project.objects.get(pk=self.kwargs["project_pk"])  # missing project → 403, not 500
```

## Exposing model attributes to policies

Models opt in to exposing attributes with `authz_fields()`, and pull related
entities into the request with `authz_related_entities()`:

```python
class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    status = models.CharField(max_length=20)

    def authz_fields(self):
        return {"status": self.status, "project": str(self.project_id)}

    def authz_related_entities(self):
        return [self.project]
```

```cedar
permit(principal, action == Action::"CloseTask", resource is Task)
when { resource.status == "open" };
```

## Multi-hop attribute paths

Policies can follow references any number of hops, on either side of the
request:

```cedar
forbid(principal, action, resource is Report)
when { resource.period.organisation.billing_status == "suspended" };

permit(principal, action == Action::"ApproveReport", resource is Report)
when { principal.profile.organisation == resource.period.organisation };
```

Each hop needs two things: an attribute holding an entity reference
(`entity_ref(obj)` builds one), and the referenced model reaching the request
so Cedar can read its attributes.

**Resource side.** Each model returns its references from `authz_fields()`
and the models behind them from `authz_related_entities()`. django-cedar
follows these transitively, so every model on the path declares its own next
hop:

```python
from django_cedar import entity_ref


class Report(models.Model):
    def authz_fields(self):
        return {"period": entity_ref(self.period)}

    def authz_related_entities(self):
        return [self.period]


class ReportingPeriod(models.Model):
    def authz_fields(self):
        return {"organisation": entity_ref(self.organisation)}

    def authz_related_entities(self):
        return [self.organisation]


class Organisation(models.Model):
    def authz_fields(self):
        return {"billing_status": self.billing_status}
```

**Principal side.** A principal attribute provider adds the first hop as an
attribute and returns the model behind it from `get_entities()`. Models
returned there are walked exactly like resources, so from `Profile` onwards
the models' own `authz_fields()` / `authz_related_entities()` take over:

```python
class ProfileProvider:
    def get_attributes(self, user):
        return {"profile": entity_ref(user.profile)}

    def get_entities(self, user):
        return [user.profile]  # Profile -> Organisation -> ... are followed
```

`get_entities()` may also return hand-built `Entity` objects, as before;
they're used as-is and not walked. A provider can return both.

The principal and resource walks share one record of what they've visited:
cycles (A → B → A) stop, a model reached from both sides is built once, and
a chain that reaches a user (`resource.owner.profile...`) carries on through
the principal attribute providers for that user.

**Duplicates.** When the same entity arrives by more than one route (for
example a provider's hand-built `Organisation` and the resource walk's
`Organisation` model), the copies are merged: attributes merge recursively
through records, and parents are unioned. If two copies give the same
attribute different values, the first value wins and a warning names the
entity type and attribute. Entities arrive in this order: hand-built `Entity`
objects from providers (in provider order), the principal and its groups,
the principal's related models, then the resource walk. So a hand-built
entity keeps every value it set, as in 0.3.0, and the models only add the
attributes it lacks.

## When a policy errors

If evaluating a policy errors — an attribute or entity on its path isn't in
the request, or a value has the wrong type — Cedar skips that policy. For a
`permit` that only means it doesn't allow. For a `forbid` the request is
**allowed** when it should have been denied. The usual cause is a model on a
multi-hop path that doesn't declare its next hop.

django-cedar logs every skipped policy at `ERROR` level on the
`django_cedar.authz` logger, with Cedar's policy id (`policy0`, `policy1`, …
in file order), its effect, its `@id("...")` annotation if it has one, the
action, and the reason with entity ids and string values redacted.

With `CEDAR_RAISE_ON_FORBID_ERROR` on, a skipped `forbid` also raises
`django_cedar.ForbidPolicyError`. It isn't a `PermissionDenied`, so it
surfaces as a server error rather than passing for an ordinary 403. It's on
by default when `DEBUG` is true and under Django's test runner or
pytest-django, so tests fail loudly instead of allowing. Turn it on in
production to fail closed (a 500 instead of an allow), or set it to `False`
to keep Cedar's skip-and-log behaviour everywhere. Guard optional attributes
with `has` (`resource has archived && resource.archived`) so that a
missing attribute is a policy decision, not an error.

## Settings

| Setting | Required | Description |
|---|---|---|
| `CEDAR_POLICY_PATH` | yes | Path to the Cedar policy file. Relative paths resolve against `BASE_DIR`. |
| `CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS` | no | List of dotted paths to classes with `get_attributes(user) -> dict` (extra principal attributes) and optionally `get_entities(user)`, returning an iterable of `Entity` objects (used as-is) and/or model instances (walked like resources; see [Multi-hop attribute paths](#multi-hop-attribute-paths)). |
| `CEDAR_CONTEXT_PROVIDERS` | no | List of dotted paths to classes with `get_context(user, action, resource) -> dict`. Results are deep-merged into the Cedar request context in list order; a per-call `context=` argument merges last and wins. |
| `CEDAR_RAISE_ON_FORBID_ERROR` | no | Raise `ForbidPolicyError` when a `forbid` policy errors during evaluation instead of letting Cedar skip it. Defaults to on under `DEBUG` and test runners, off otherwise. See [When a policy errors](#when-a-policy-errors). |

Example context provider:

```python
class FeatureFlagContext:
    def get_context(self, user, action, resource):
        return {"allow": {"self_signup": settings.ALLOW_SELF_SIGNUP}}
```

## Using the engine directly

```python
from django_cedar import create_authz

authz = create_authz()  # loads policies + providers from settings (cached)
authz.authorize(request.user, "ExportReport", report)  # raises PermissionDenied on deny
```

`Authz(..., raise_on_forbid_error=True)` overrides `CEDAR_RAISE_ON_FORBID_ERROR`
for one engine.

## System checks

With `django_cedar` in `INSTALLED_APPS`, `manage.py check` (and every server
start) verifies that `CEDAR_POLICY_PATH` is set and the file exists
(`django_cedar.E001`/`E002`), that it parses as Cedar (`E003`), that the
provider settings are lists or tuples (`E006`), and that all configured
providers import and have the right methods (`E004`/`E005`).

## License

Apache-2.0
