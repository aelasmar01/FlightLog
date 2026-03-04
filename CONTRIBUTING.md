# Contributing to Flightlog

Thank you for your interest in contributing!

## Workflow

1. **Pick an issue** from the [backlog](https://github.com/aelasmar01/ReplayKit/issues).
2. **Create a branch** named `issue/<NN>-<slug>` (e.g., `issue/25-sse-streaming`).
3. **Implement** the deliverables described in the issue.
4. **Every commit must pass** the quality gate:

   ```bash
   uv run ruff check . && uv run ruff format --check . && uv run mypy flightlog && uv run pytest -q
   ```

5. **Open a PR** to `main`. CI must be green before merge.
6. **Do not start the next issue** until the previous PR is merged and `main` is green.

## Branch naming

```
issue/<NN>-<short-slug>
```

Examples:
- `issue/25-sse-streaming`
- `issue/26-wrap-http`
- `issue/27-discovery-cursor-zed`

## Commit style

- Use imperative mood: "Add streaming support" not "Added streaming support".
- Keep the first line ≤ 72 characters.
- Reference the issue: `Closes #NN` or `Part of #NN` in the body.

## Code standards

| Tool | Command |
|------|---------|
| Linting | `uv run ruff check .` |
| Formatting | `uv run ruff format .` |
| Type checking | `uv run mypy flightlog` |
| Tests | `uv run pytest -q` |

- Tests live in `tests/`.
- Fixtures live in `tests/fixtures/`.
- Every new module must have corresponding tests.
- Do not commit secrets or real API keys — even in test fixtures.

## Setting up locally

```bash
git clone https://github.com/aelasmar01/ReplayKit.git
cd ReplayKit
uv sync --all-extras
uv run pre-commit install
```

## Reporting bugs

Open a GitHub Issue with:
- Steps to reproduce
- Expected vs actual behaviour
- `flightlog --version` output (once released)
- OS and Python version
