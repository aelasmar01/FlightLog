# ReplayPack Examples

Self-contained sample fixtures and a step-by-step walkthrough.

## Files

| File | Description |
|------|-------------|
| `sample_claude_session.jsonl` | Minimal Claude Code session log with a model request and a file change. |
| `sample_mcp_transcript.jsonl` | Recorded MCP JSON-RPC transcript with two methods across three calls. |
| `fake_mcp_server.py` | Minimal stdio echo MCP server for live-capture examples. |

---

## Walkthrough

All commands run from the repo root with `uv sync` already completed.

### Phase 1 — Build a pack from logs

**1. Build a pack from the sample Claude session:**

```bash
uv run replaypack pack build \
  --input examples/sample_claude_session.jsonl \
  --out /tmp/rp-demo
```

**2. Validate pack integrity:**

```bash
uv run replaypack pack validate --path /tmp/rp-demo
```

**3. View file diffs captured in the pack:**

```bash
uv run replaypack pack diff --pack /tmp/rp-demo --list
uv run replaypack pack diff --pack /tmp/rp-demo --file src/app.py
```

**4. Build with redaction applied:**

```bash
uv run replaypack pack build \
  --input examples/sample_claude_session.jsonl \
  --out /tmp/rp-redacted \
  --redaction redaction.yml.example
```

---

### Phase 2 — MCP Capture & Replay

**5. Generate a stub directly from the sample transcript:**

```bash
uv run replaypack mcp stub generate \
  --transcript examples/sample_mcp_transcript.jsonl \
  --out /tmp/rp-stub.json
```

**6. Wrap the fake echo server and capture a live transcript:**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tool.alpha","params":{"x":1}}' | \
  uv run replaypack mcp wrap \
    --name my-server \
    --out /tmp/rp-mcp \
    -- python examples/fake_mcp_server.py
```

The captured transcript appears under `/tmp/rp-mcp/mcp/transcripts/my-server/`.

**7. Generate a stub from the captured transcript:**

```bash
uv run replaypack mcp stub generate \
  --transcript /tmp/rp-mcp/mcp/transcripts/my-server/<session>.jsonl \
  --out /tmp/rp-mcp/mcp/stubs/my-server/session.json
```

**8. Serve the stub as an offline MCP server:**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tool.alpha","params":{"x":1}}' | \
  uv run replaypack mcp stub serve \
    --stub /tmp/rp-mcp/mcp/stubs/my-server/session.json
```

**9. Run an offline replay:**

```bash
uv run replaypack replay run --pack /tmp/rp-demo --offline
```
