from django.apps import AppConfig


class DjangoCedarConfig(AppConfig):
    name = "django_cedar"
    verbose_name = "Django Cedar"

    def ready(self) -> None:
        # Importing the module registers the system checks.
        from django_cedar import checks  # noqa: F401
