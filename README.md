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

- **principal** — `User::"<pk>"` for authenticated users, `Anonymous::"guest"`
  otherwise. User entities carry `id`, `is_staff` and `is_superuser`
  attributes, and the user's Django groups become parent entities
  (`Group::"<name>"`), so `principal in Group::"editors"` works out of the box.
- **action** — `Action::"<name>"` from the view's `action_names` mapping
  (HTTP method → action name). HEAD requests are authorized using the view's
  `"GET"` action mapping; a `"HEAD"` key in `action_names` is not consulted.
- **resource** — the object returned by the view's `get_resource()` hook, as
  `<ModelClass>::"<pk>"`; `System::"global"` when there is no resource.

Denied requests raise `django.core.exceptions.PermissionDenied` (HTTP 403).

## Views and mixins

| Class | Resource used for the check |
|---|---|
| `AuthorizedDetailView` / `AuthorizedUpdateView` / `AuthorizedDeleteView` | `self.get_object()` |
| `AuthorizedListView` / `AuthorizedCreateView` / `AuthorizedTemplateView` / `AuthorizedFormView` | `System::"global"` (override `get_resource()`) |

Compose the behavior yourself with `CedarAuthorizationMixin` plus:

- `ResourceIsCurrentObjectMixin` — authorize against `self.get_object()`.
- `CurrentUserScopedMixin` — authorize against the current user and filter
  the queryset to `user=<request.user>`.
- `AsyncLoginRequiredMixin` — a `LoginRequiredMixin` that works on async
  views. `CedarAuthorizationMixin` itself supports async views too.

Custom scoping is one method:

```python
class ProjectScopedView(CedarAuthorizationMixin, ListView):
    action_names = {"GET": "ListTasks"}

    def get_resource(self, request):
        return Project.objects.get(pk=self.kwargs["project_pk"])
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

## Settings

| Setting | Required | Description |
|---|---|---|
| `CEDAR_POLICY_PATH` | yes | Path to the Cedar policy file. Relative paths resolve against `BASE_DIR`. |
| `CEDAR_PRINCIPAL_ATTRIBUTE_PROVIDERS` | no | List of dotted paths to classes with `get_attributes(user) -> dict` (extra principal attributes) and optionally `get_entities(user) -> iterable[Entity]` (extra entities). |
| `CEDAR_CONTEXT_PROVIDERS` | no | List of dotted paths to classes with `get_context(user, action, resource) -> dict`. Results are deep-merged into the Cedar request context in list order; a per-call `context=` argument merges last and wins. |

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

## System checks

With `django_cedar` in `INSTALLED_APPS`, `manage.py check` (and every server
start) verifies that `CEDAR_POLICY_PATH` is set and the file exists
(`django_cedar.E001`/`E002`), that it parses as Cedar (`E003`), that the
provider settings are lists or tuples (`E006`), and that all configured
providers import and have the right methods (`E004`/`E005`).

## License

Apache-2.0
