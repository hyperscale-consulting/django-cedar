from __future__ import annotations

import os
import subprocess
import sys


def test_import_without_django_settings():
    """The package must be importable before django.setup() / settings config.

    Django imports the package during app loading, when models are not yet
    ready — so the top-level package must not import Django models eagerly.
    """
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    result = subprocess.run(
        [sys.executable, "-c", "import django_cedar"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
