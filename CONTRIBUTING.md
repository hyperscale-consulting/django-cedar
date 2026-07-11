# Contributing

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
git clone https://github.com/hyperscale-consulting/django-cedar.git
cd django-cedar
uv sync
uvx pre-commit install
```

## Running checks

```bash
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format --check .   # formatting
uv run pyright                 # types
```

Test against a specific Django line:

```bash
uv run --with "django~=5.2.0" pytest
uv run --with "django~=6.0.0" pytest
```

CI runs the full matrix (Python 3.12–3.14 × Django 5.2/6.0) on every PR.

## Pull requests

- Add tests for behavior changes.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Keep the public API documented in `README.md`.
