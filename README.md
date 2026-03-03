# Flightlog

Flightlog is a privacy-first "HAR/crash-dump for agents" CLI.

It builds portable replay packs from local logs, redacts sensitive material, captures MCP wire traffic, and supports offline replay against deterministic MCP stubs.

## Quickstart

### 1. Install dependencies

```bash
uv sync --all-extras
```

### 2. Build a pack from JSONL logs

```bash
uv run flightlog pack build \
  --input tests/fixtures/claude_code/claude_session.jsonl \
  --out /tmp/flightlog-demo
```

### 3. Validate pack integrity

```bash
uv run flightlog pack validate --path /tmp/flightlog-demo
```

### 4. List or render diffs in a pack

```bash
uv run flightlog pack diff --pack /tmp/flightlog-demo --list
uv run flightlog pack diff --pack /tmp/flightlog-demo --file src/app.py
```

## Live Tail (Issue 18)

```bash
uv run flightlog watch \
  --input tests/fixtures/claude_code/claude_session.jsonl \
  --from-start \
  --max-events 2
```

To continuously update a pack while tailing:

```bash
uv run flightlog watch \
  --input tests/fixtures/claude_code/claude_session.jsonl \
  --out /tmp/flightlog-live-pack
```

## Compare and Assert (Issues 19, 20)

```bash
uv run flightlog pack compare \
  --baseline /tmp/flightlog-baseline \
  --candidate /tmp/flightlog-candidate

uv run flightlog assert \
  --baseline /tmp/flightlog-baseline \
  --candidate /tmp/flightlog-candidate \
  --policy policy.yml
```

## Audit Export and Signing (Issues 21, 22)

```bash
uv run flightlog export audit \
  --pack /tmp/flightlog-demo \
  --out /tmp/audit.json \
  --csv /tmp/audit.csv \
  --config audit.yml

uv run flightlog sign --pack /tmp/flightlog-demo --key private_ed25519.pem
uv run flightlog verify --pack /tmp/flightlog-demo --key public_ed25519.pem
```

## Redaction

Use `redaction.yml.example` as a template:

```bash
uv run flightlog pack build \
  --input tests/fixtures/claude_code/claude_session.jsonl \
  --out /tmp/flightlog-demo \
  --redaction redaction.yml.example
```

## Guaranteed Diffs

If logs do not contain patch content, provide workspace snapshots:

```bash
uv run flightlog pack build \
  --input tests/fixtures/diffs/snapshot/no_diff.jsonl \
  --out /tmp/flightlog-snap \
  --workspace-before tests/fixtures/diffs/snapshot/workspace_before \
  --workspace-after tests/fixtures/diffs/snapshot/workspace_after
```

## Model Event Schema

`model.request` and `model.response` payloads are provider-agnostic.
Schema details: [`docs/event_schema.md`](docs/event_schema.md).

## MCP Capture & Replay

### Wrap a stdio MCP server and capture transcript

```bash
uv run flightlog mcp wrap --name demo --out /tmp/flightlog-mcp -- python path/to/server.py
```

### Generate stub from transcript

```bash
uv run flightlog mcp stub generate \
  --transcript /tmp/flightlog-mcp/mcp/transcripts/demo/<session>.jsonl \
  --out /tmp/flightlog-mcp/mcp/stubs/demo/<session>.json
```

### Serve stub

```bash
uv run flightlog mcp stub serve --stub /tmp/flightlog-mcp/mcp/stubs/demo/<session>.json
```

### Offline replay

```bash
uv run flightlog replay run --pack /tmp/flightlog-demo --offline
```

## MCP Discovery

```bash
uv run flightlog mcp list
```

## Packaging and Release (Issue 23)

Build artifacts locally:

```bash
uv run --with build python -m build
```

Install directly from GitHub:

```bash
pipx install 'git+https://github.com/aelasmar01/FlightLog.git'
```

Tag-based release workflow (`v*`) builds `sdist`/`wheel`, publishes GitHub Releases, and publishes to PyPI when `PYPI_API_TOKEN` is configured.

## Roadmap (Issue 24)

See [`docs/roadmap.md`](docs/roadmap.md) for tracked backlog/status and issue links.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy flightlog
uv run pytest -q
```
