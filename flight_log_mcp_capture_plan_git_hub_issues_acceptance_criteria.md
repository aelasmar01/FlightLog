# Replay Pack + MCP Capture & Replay — Implementation Plan (GitHub Issues)

> **Purpose**: This document is written for a coding agent (Codex) to implement a production-grade **Replay Pack** tool with a new **Phase 2: MCP Capture & Replay** capability.
>
> **Non-negotiables**
> - Every feature below is a **GitHub Issue**.
> - **One branch per issue**: `issue/<NN>-<slug>`.
> - Every commit must pass all tests **before** proceeding.
> - Every PR merge to `main` must pass **full CI**.
> - Use explicit completion requirements and tests for each issue.
>
> **Primary Goal**: Build a portable, privacy-first “HAR/crash-dump for agents” that can be generated from local agent logs (Phase 1) and augmented with deterministic **MCP wire transcript capture + stub replay** (Phase 2).

---

## 0) Repo Standards (apply to all issues)

### Tech stack
- Python **3.11+**
- `uv` for env + deps
- `ruff` + `mypy` + `pytest`
- `pre-commit`
- Packaging: `pyproject.toml` (PEP 621)

### Testing and quality gates
- `pytest -q` must pass locally and in CI.
- `ruff check .` and `ruff format --check .` must pass.
- `mypy` must pass.
- `pytest` must include unit tests; add integration tests where specified.

### Branch/PR rules
- Each issue branch must include:
  - Implementation
  - Tests
  - Docs/CLI help updates
- PR must pass CI and must not reduce coverage.

### CLI naming
Assume binary name is `flightlog`.

---

## 1) High-level Architecture

### Core concepts
- **Replay Pack**: a versioned directory (optionally zipped) containing:
  - `manifest.json` (metadata + invariant hashes)
  - `timeline.jsonl` (normalized events)
  - `artifacts/` (redacted copies: prompts, responses, tool IO, diffs)
  - `redaction_report.json` (what was removed/masked)
  - optional `mcp/` folder (wire transcripts + derived stubs)

### Event Model (normalized)
Events emitted into `timeline.jsonl` must use a stable schema:
- `event_id` (uuid)
- `ts` (RFC3339)
- `source` (e.g., `claude_code`, `codex_cli`, `mcp_wire`)
- `type` (e.g., `model.request`, `model.response`, `tool.call`, `tool.result`, `mcp.request`, `mcp.response`, `file.diff`)
- `session_id` (string)
- `run_id` (string)
- `payload` (object)

### Deterministic invariants
- Manifest includes SHA256 hashes for `timeline.jsonl` and all stored artifacts.
- Manifest includes `schema_version`.

---

# Issues

## Issue 01 — Repository bootstrap, CI, and tooling

### Objective
Create a clean Python repo with CI, formatting, linting, typing, and test harness.

### Deliverables
- `pyproject.toml` with `uv`-compatible dependencies.
- `ruff` config (lint + format).
- `mypy` config.
- `pytest` config.
- `pre-commit` config.
- GitHub Actions workflow running: `ruff`, `mypy`, `pytest`.

### Completion requirements
- `uv sync` works.
- `pre-commit run --all-files` passes.
- CI passes on `main`.

### Tests
- Add a trivial `test_smoke.py` that always passes to validate harness.

---

## Issue 02 — Core domain models (schema + manifest)

### Objective
Define stable schemas for replay packs and normalized events, plus serialization helpers.

### Deliverables
- `flightlog/models.py` with Pydantic v2 models (or dataclasses + jsonschema if preferred). Must include:
  - `FlightlogManifest`
  - `NormalizedEvent`
  - `RedactionReport`
- `flightlog/schema_version.py`
- JSON serialization/deserialization helpers.

### Completion requirements
- Models validate and serialize deterministically.
- `manifest.json` produced by helper matches model.

### Tests
- Unit tests that:
  - round-trip serialize/deserialize for each model
  - ensure stable key ordering in JSON output (if enforced)

---

## Issue 03 — Replay Pack writer (directory + zip) with hashing

### Objective
Implement a pack writer that writes the pack directory, computes hashes, and optionally zips it.

### Deliverables
- `flightlog/pack_writer.py`
  - `create_pack(output_dir, events_iter, artifacts, redaction_report, extra_sections)`
  - writes `timeline.jsonl` and `manifest.json`
  - calculates SHA256 for each artifact and timeline
  - supports `--zip` output: `pack.zip`

### Completion requirements
- Creating a pack produces:
  - `manifest.json`
  - `timeline.jsonl`
  - `artifacts/` (even if empty)
- Hashes in manifest match actual file contents.

### Tests
- Integration test that creates a pack with 2 events and 1 artifact, validates:
  - required files exist
  - hash equality
  - zip output contains same structure

---

## Issue 04 — Redaction engine (masking + allow/deny rules)

### Objective
Implement privacy-first redaction that runs **before** writing artifacts.

### Rules
- Default-deny: redact secrets and PII patterns.
- Support configurable rules via `redaction.yml`.
- Must support:
  - regex-based redaction (mask groups)
  - JSON key-based redaction (e.g., `"api_key"`, `"authorization"`)
  - file-path exclusions (do not include certain artifacts)

### Deliverables
- `flightlog/redaction.py`
- `redaction.yml.example`
- `redaction_report.json` builder

### Completion requirements
- Running redaction on known secret samples masks them.
- Report includes:
  - patterns matched
  - number of replacements
  - list of excluded artifacts

### Tests
- Unit tests for:
  - regex masking
  - json-key masking
  - exclusion logic
  - report content

---

## Issue 05 — CLI skeleton: `flightlog pack build` + help + logging

### Objective
Create the CLI and wire it to pack writer + redaction.

### Deliverables
- `flightlog/cli.py` using Typer (or Click).
- Commands:
  - `flightlog --help`
  - `flightlog pack --help`
  - `flightlog pack build --input <path> --out <dir|zip> [--zip] [--redaction <yml>]`
- Structured logs (JSON option) and human logs.

### Completion requirements
- `flightlog pack build` runs end-to-end on fixture input and produces a valid pack.

### Tests
- CLI tests using `pytest` + `typer.testing.CliRunner`:
  - `--help` exits 0
  - build produces outputs

---

## Issue 06 — Phase 1 log ingestion: Claude Code JSONL parser

### Objective
Parse Claude Code local logs into normalized events.

### Scope
- Detect sessions and build `session_id`/`run_id`.
- Map tool use/result, model request/response.

### Deliverables
- `flightlog/ingest/claude_code.py`
  - `detect(input_path) -> bool`
  - `iter_events(input_path) -> Iterator[NormalizedEvent]`
  - `extract_artifacts(...) -> dict`

### Completion requirements
- Provided fixture logs produce deterministic `timeline.jsonl`.

### Tests
- Golden file test:
  - Given `fixtures/claude_code/*.jsonl`, output `timeline.jsonl` matches `expected_timeline.jsonl`.

---

## Issue 07 — Phase 1 log ingestion: Codex-style session log parser (generic)

### Objective
Implement a second ingestor for “codex-like” logs (generic JSONL structure).

### Deliverables
- `flightlog/ingest/generic_jsonl.py`
- Auto-select ingestor based on detection.

### Completion requirements
- If both parsers can detect, selection is deterministic and documented.

### Tests
- Fixtures + golden output.

---

## Issue 08 — Timeline normalization + artifact extraction + guaranteed diffs + diff viewer

### Objective
Make Phase 1 **always** produce viewable, git-style diffs when file changes exist, and provide a CLI to view them.

This issue **bakes in** the requirement that diffs are not “best-effort.” If the logs don’t contain enough information, Phase 1 must be able to compute diffs using workspace snapshots provided by the user.

### Deliverables
- `flightlog/normalize.py`
  - Artifact policy:
    - if a payload > `ARTIFACT_THRESHOLD_BYTES`, store under `artifacts/` and replace inline payload with an artifact reference.
  - File diff extraction pipeline that supports two sources of truth:
    1) **Log-derived diffs** (preferred): if logs include before/after content or patch/delta info.
    2) **Snapshot-derived diffs** (required fallback): if the user provides workspace snapshots.

- **New CLI flags (Phase 1)** on `flightlog pack build`:
  - `--workspace-before <dir>`: directory snapshot of the workspace **before** the run.
  - `--workspace-after <dir>`: directory snapshot of the workspace **after** the run.
  - Behavior:
    - If *both* are provided, Phase 1 must compute diffs for any changed file path referenced in events (and may optionally compute a full directory diff if configured).
    - If diffs are available from logs, prefer log-derived diffs.

- Diff artifact storage:
  - Store unified diffs as patch files:
    - `artifacts/diffs/<normalized_path>.<event_id>.patch`
  - Emit `file.diff` events referencing the patch artifact.

- **New CLI command (Phase 1 viewer)**:
  - `flightlog pack diff --pack <dir|zip> [--file <path>] [--event <event_id>] [--list]`
  - Expected behavior:
    - `--list` prints changed files (path + ts + event_id).
    - `--file` prints all diffs for that file.
    - `--event` prints the specific diff artifact for that event.
    - Exit code non-zero if no diffs exist / not found.

### Completion requirements
- Timeline entries remain small and reference artifacts.
- **Guaranteed diff rule**:
  - For fixture runs where a file changes, the generated pack MUST contain at least one valid unified diff artifact with headers (`---`, `+++`, `@@`).
  - If the ingested logs do not provide diff content, providing `--workspace-before` and `--workspace-after` MUST still result in valid unified diff artifacts.
- `flightlog pack diff --list` and `--file` must work on the generated pack.

### Tests
- Artifact extraction test: payloads larger than threshold become artifacts.
- Diff generation tests:
  1) **Log-derived diff** fixture: ensure the patch artifact is produced and matches `expected.patch`.
  2) **Snapshot-derived diff** fixture: provide `workspace_before/` and `workspace_after/` directories; ensure unified diff is produced even if logs lack diff data.
- CLI tests:
  - `flightlog pack diff --list` prints expected file(s).
  - `flightlog pack diff --file <path>` prints unified diff with `---/+++` and `@@`.
  - Non-zero exit when requesting a missing file/event.


---

## Issue 09 — Pack validation command: `flightlog pack validate`

### Objective
Validate structure and hashes.

### Deliverables
- `flightlog pack validate --path <pack_dir_or_zip>`
- Validations:
  - manifest present
  - timeline present
  - hashes match
  - schema version supported

### Completion requirements
- Validation returns non-zero on any mismatch.

### Tests
- Corrupt a file after creation and assert validate fails.

---

# Phase 2 — MCP Capture & Replay

## Issue 10 — MCP model + transcript storage format

### Objective
Define a storage format for MCP wire transcripts and derived stubs.

### Deliverables
- `flightlog/mcp/models.py`:
  - `McpMessage` (request/response/notification)
  - `McpTranscript` (session metadata + list of messages)
- Storage under pack:
  - `mcp/transcripts/<server_name>/<session_id>.jsonl`
  - `mcp/stubs/<server_name>/<session_id>.json`

### Completion requirements
- Transcripts are append-friendly JSONL.
- Stubs are deterministic.

### Tests
- Round-trip transcript serialization.
- Deterministic stub generation test.

---

## Issue 11 — MCP wrapper/launcher for stdio JSON-RPC servers

### Objective
Provide a wrapper that runs an MCP server process and captures **all stdin/stdout JSON-RPC** messages.

### CLI
- `flightlog mcp wrap --name <server> -- <cmd ...>`
  - runs the command
  - proxies stdin/stdout
  - writes transcript file

### Deliverables
- `flightlog/mcp/wrap_stdio.py`
- CLI integration.

### Completion requirements
- Wrapper does not break the server protocol.
- Captures every JSON-RPC line from both directions.
- Handles partial reads / buffering robustly.

### Tests
- Create a fake MCP server fixture (simple JSON-RPC echo) launched by tests.
- Assert transcript includes expected request/response pairs.

---

## Issue 12 — MCP HTTP proxy mode (optional) for HTTP-transport servers

### Objective
Support MCP servers that communicate over HTTP (if applicable in target clients).

### CLI
- `flightlog mcp proxy --listen 127.0.0.1:PORT --upstream http://... --name <server>`

### Deliverables
- `flightlog/mcp/proxy_http.py` using `httpx`.

### Completion requirements
- Transparent proxying with full body capture.
- Redaction applied to stored transcript.

### Tests
- Spin up a minimal HTTP JSON-RPC server in tests.
- Assert proxy captures requests/responses.

---

## Issue 13 — Generate deterministic MCP stubs from transcripts

### Objective
Convert captured wire transcripts into replay stubs that can answer tool calls deterministically.

### Behavior
- For each JSON-RPC `method`, map request params signature -> stored response.
- Matching strategy:
  - exact match on `method` + stable hash of canonicalized params
  - fallback: allow regex-like match rules in a stub config file

### Deliverables
- `flightlog/mcp/stubgen.py`
- Output stub file written under `mcp/stubs/...`.

### Completion requirements
- Stub generation is deterministic.
- Can handle repeated calls to same method with different params.

### Tests
- Given transcript fixture with 3 calls, stub contains 3 mappings.
- Canonicalization is stable (key order independent).

---

## Issue 14 — MCP stub server for replay (stdio)

### Objective
Provide a fake MCP server that serves responses from the stub mapping.

### CLI
- `flightlog mcp stub serve --stub <stub.json>`

### Deliverables
- `flightlog/mcp/stub_server.py`

### Completion requirements
- Implements JSON-RPC read loop.
- Returns correct response for known request.
- Returns JSON-RPC error for unknown mapping.

### Tests
- Launch stub server in tests, send JSON-RPC request, assert response.

---

## Issue 15 — `flightlog replay run` (offline replay runner)

### Objective
Replay a run offline:
- Load pack
- Re-emit timeline
- When MCP calls appear, route them to stub server (no real network)

### CLI
- `flightlog replay run --pack <dir|zip> --offline`

### Deliverables
- `flightlog/replay_runner.py`

### Completion requirements
- Replayer runs without external dependencies beyond the pack.
- Reports mismatches if events differ.

### Tests
- Build a pack from fixtures with MCP transcript; run replay; assert success.

---

## Issue 16 — MCP discovery helpers (client configs)

### Objective
Add utilities to detect configured MCP servers for common clients.

### Scope (start minimal)
- Support a config discovery for at least one client (documented path).
- Provide `flightlog mcp list` to show discovered servers.

### Completion requirements
- Does not crash on missing configs.
- Produces stable output.

### Tests
- Use temp directories as fake configs.

---

## Issue 17 — End-to-end demo + docs

### Objective
Document and provide a demo path:
- Build pack from logs
- Wrap MCP server to record transcript
- Generate stub
- Replay offline

### Deliverables
- `README.md` with:
  - quickstart
  - redaction config
  - MCP wrap instructions
  - replay instructions
- `examples/` folder with sample fixtures.

### Completion requirements
- A reviewer can follow README and reproduce pack build + replay.

### Tests
- “Docs smoke” test: ensure example commands in README are runnable in CI using fixtures (where feasible).

---

# Definition of Done (global)
- All issues completed on their own branch.
- Each issue includes tests.
- All tests pass on every commit.
- Every PR merge to `main` passes CI.
- No secret material is stored unredacted in fixtures.

---

# Final instruction to the coding agent (Codex)

1. Create a GitHub issue for each **Issue NN** in this document.
2. For each issue:
   - Create branch `issue/<NN>-<slug>`.
   - Implement exactly the described deliverables.
   - Add/modify tests so the issue is verifiably complete.
   - Run `ruff`, `mypy`, `pytest` locally; fix until green.
   - Open PR to `main`; ensure CI is green; merge.
3. Do not start the next issue until the previous PR is merged and `main` is green.

