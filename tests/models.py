from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AbstractUser
from django.db import models


class Member(AbstractUser):
    """Custom full-featured user model for AUTH_USER_MODEL swap tests.

    The related_name overrides avoid reverse-accessor clashes with the
    concurrently installed default ``auth.User`` model.
    """

    groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="member_set",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        blank=True,
        related_name="member_set",
    )


class Device(AbstractBaseUser):
    """Bare user model: no is_staff/is_superuser, no groups."""

    identifier = models.CharField(max_length=64, unique=True)

    USERNAME_FIELD = "identifier"
