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

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy flightlog
uv run pytest -q
```
