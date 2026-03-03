# Flightlog Examples

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
uv run flightlog pack build \
  --input examples/sample_claude_session.jsonl \
  --out /tmp/rp-demo
```

**2. Validate pack integrity:**

```bash
uv run flightlog pack validate --path /tmp/rp-demo
```

**3. View file diffs captured in the pack:**

```bash
uv run flightlog pack diff --pack /tmp/rp-demo --list
uv run flightlog pack diff --pack /tmp/rp-demo --file src/app.py
```

**4. Build with redaction applied:**

```bash
uv run flightlog pack build \
  --input examples/sample_claude_session.jsonl \
  --out /tmp/rp-redacted \
  --redaction redaction.yml.example
```

**5. Live-tail a session and update a pack incrementally:**

```bash
uv run flightlog watch \
  --input examples/sample_claude_session.jsonl \
  --out /tmp/rp-live \
  --from-start \
  --max-events 2
```

**6. Compare two packs and apply a CI-style assertion policy:**

```bash
uv run flightlog pack compare \
  --baseline /tmp/rp-demo \
  --candidate /tmp/rp-redacted \
  --format json

uv run flightlog assert \
  --baseline /tmp/rp-demo \
  --candidate /tmp/rp-redacted
```

---

### Phase 2 — MCP Capture & Replay

**7. Generate a stub directly from the sample transcript:**

```bash
uv run flightlog mcp stub generate \
  --transcript examples/sample_mcp_transcript.jsonl \
  --out /tmp/rp-stub.json
```

**8. Wrap the fake echo server and capture a live transcript:**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tool.alpha","params":{"x":1}}' | \
  uv run flightlog mcp wrap \
    --name my-server \
    --out /tmp/rp-mcp \
    -- python examples/fake_mcp_server.py
```

The captured transcript appears under `/tmp/rp-mcp/mcp/transcripts/my-server/`.

**9. Generate a stub from the captured transcript:**

```bash
uv run flightlog mcp stub generate \
  --transcript /tmp/rp-mcp/mcp/transcripts/my-server/<session>.jsonl \
  --out /tmp/rp-mcp/mcp/stubs/my-server/session.json
```

**10. Serve the stub as an offline MCP server:**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tool.alpha","params":{"x":1}}' | \
  uv run flightlog mcp stub serve \
    --stub /tmp/rp-mcp/mcp/stubs/my-server/session.json
```

**11. Run an offline replay:**

```bash
uv run flightlog replay run --pack /tmp/rp-demo --offline
```

---

### Governance and Signing

**12. Export a deterministic audit report (JSON/CSV):**

```bash
uv run flightlog export audit \
  --pack /tmp/rp-demo \
  --out /tmp/audit.json \
  --csv /tmp/audit.csv
```

**13. Sign and verify a pack (Ed25519):**

```bash
uv run flightlog sign --pack /tmp/rp-demo --key private_ed25519.pem
uv run flightlog verify --pack /tmp/rp-demo --key public_ed25519.pem
```
