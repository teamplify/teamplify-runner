# Development

This document is for maintainers of the teamplify-runner project.

## Releasing a new version

Releases are automated via GitHub Actions. To publish a new version to PyPI:

1. Update the `version` in `pyproject.toml`
2. Commit and push to `master`

The CI workflow will:
- Run all tests
- Check if the version in `pyproject.toml` is higher than what's on PyPI
- If yes, build and publish the new version

No manual PyPI uploads or tags required. The version in `pyproject.toml` is the single source of truth.

## Local development

Install dependencies:

```bash
uv sync --group dev
```

Run tests:

```bash
uv run pytest --ignore tests/test_startup.py
```

Run linting:

```bash
uv run ruff check
uv run ruff format --check
```

Format code:

```bash
uv run ruff format
```

It's a good idea to set up automatic code formatting in your IDE, as well as configure a pre-commit hook that runs ruff (both linter and format check).
