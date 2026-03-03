# ReplayPack

ReplayPack is a privacy-first "HAR/crash-dump for agents" CLI.

It builds portable replay packs from local logs, redacts sensitive material, captures MCP wire traffic, and supports offline replay against deterministic MCP stubs.

## Quickstart

### 1. Install dependencies

```bash
uv sync --all-extras
```

### 2. Build a pack from JSONL logs

```bash
uv run replaypack pack build \
  --input tests/fixtures/claude_code/claude_session.jsonl \
  --out /tmp/replaypack-demo
```

### 3. Validate pack integrity

```bash
uv run replaypack pack validate --path /tmp/replaypack-demo
```

### 4. List or render diffs in a pack

```bash
uv run replaypack pack diff --pack /tmp/replaypack-demo --list
uv run replaypack pack diff --pack /tmp/replaypack-demo --file src/app.py
```

## Redaction

Use `redaction.yml.example` as a template:

```bash
uv run replaypack pack build \
  --input tests/fixtures/claude_code/claude_session.jsonl \
  --out /tmp/replaypack-demo \
  --redaction redaction.yml.example
```

## Guaranteed Diffs

If logs do not contain patch content, provide workspace snapshots:

```bash
uv run replaypack pack build \
  --input tests/fixtures/diffs/snapshot/no_diff.jsonl \
  --out /tmp/replaypack-snap \
  --workspace-before tests/fixtures/diffs/snapshot/workspace_before \
  --workspace-after tests/fixtures/diffs/snapshot/workspace_after
```

## MCP Capture & Replay

### Wrap a stdio MCP server and capture transcript

```bash
uv run replaypack mcp wrap --name demo --out /tmp/replaypack-mcp -- python path/to/server.py
```

### Generate stub from transcript

```bash
uv run replaypack mcp stub generate \
  --transcript /tmp/replaypack-mcp/mcp/transcripts/demo/<session>.jsonl \
  --out /tmp/replaypack-mcp/mcp/stubs/demo/<session>.json
```

### Serve stub

```bash
uv run replaypack mcp stub serve --stub /tmp/replaypack-mcp/mcp/stubs/demo/<session>.json
```

### Offline replay

```bash
uv run replaypack replay run --pack /tmp/replaypack-demo --offline
```

## MCP Discovery

```bash
uv run replaypack mcp list
```

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy replaypack
uv run pytest -q
```
