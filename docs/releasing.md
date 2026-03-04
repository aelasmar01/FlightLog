# Releasing Flightlog

## Pre-release checklist

- [ ] All tests pass on `main`: `uv run pytest -q`
- [ ] `ruff` and `mypy` are green: `uv run ruff check . && uv run ruff format --check . && uv run mypy flightlog`
- [ ] `SCHEMA_VERSION` in `flightlog/schema_version.py` is updated if the pack schema changed
- [ ] `CHANGELOG.md` (if maintained) is up to date
- [ ] Version in `pyproject.toml` reflects the release tag

## Bumping the version

```bash
# Edit pyproject.toml: version = "X.Y.Z"
# Edit flightlog/schema_version.py if the schema changed
git add pyproject.toml flightlog/schema_version.py
git commit -m "chore: bump version to X.Y.Z"
```

## Tagging and releasing on GitHub

```bash
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

The GitHub Actions CI will:
1. Run `ruff`, `mypy`, and `pytest`.
2. Build the wheel and sdist via `python -m build`.
3. Install the wheel into a clean venv and run `flightlog --help` (package smoke test).

## Publishing to PyPI (optional)

If `PYPI_API_TOKEN` is set as a GitHub Actions secret, add a publish step to `.github/workflows/ci.yml`:

```yaml
- name: Publish to PyPI
  if: startsWith(github.ref, 'refs/tags/')
  run: uv run twine upload dist/*
  env:
    TWINE_USERNAME: __token__
    TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
```

## Installing from GitHub (before PyPI release)

```bash
pipx install git+https://github.com/aelasmar01/ReplayKit.git
# or
pip install git+https://github.com/aelasmar01/ReplayKit.git
```

## Installing from wheel (local build)

```bash
uv run --with build python -m build
pip install dist/flightlog-*.whl
flightlog --help
```
