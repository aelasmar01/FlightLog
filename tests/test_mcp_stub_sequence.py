"""Tests for sequence-aware MCP stub generation and serving."""

from __future__ import annotations

from pathlib import Path

from flightlog.mcp.models import McpMessage
from flightlog.mcp.stub_server import _response_for_request
from flightlog.mcp.stubgen import generate_stub, load_stub, params_hash, write_stub


def _make_request(request_id: int, method: str, params: dict) -> McpMessage:
    return McpMessage(
        direction="client->server",
        kind="request",
        method=method,
        request_id=request_id,
        ts="2026-01-01T00:00:00Z",
        payload={"id": request_id, "jsonrpc": "2.0", "method": method, "params": params},
    )


def _make_response(request_id: int, result: dict) -> McpMessage:
    return McpMessage(
        direction="server->client",
        kind="response",
        method=None,
        request_id=request_id,
        ts="2026-01-01T00:00:00.1Z",
        payload={"id": request_id, "jsonrpc": "2.0", "result": result},
    )


def test_stubgen_sequence_same_params(tmp_path: Path) -> None:
    """Two identical calls should produce a list of two responses."""
    messages = [
        _make_request(1, "tool.alpha", {"x": 1}),
        _make_response(1, {"ok": True}),
        _make_request(2, "tool.alpha", {"x": 1}),
        _make_response(2, {"ok": False}),
    ]
    stub = generate_stub(messages)
    h = params_hash({"x": 1})
    seq = stub["methods"]["tool.alpha"][h]
    assert isinstance(seq, list)
    assert len(seq) == 2
    assert seq[0] == {"result": {"ok": True}}
    assert seq[1] == {"result": {"ok": False}}


def test_stubgen_different_params_not_collapsed(tmp_path: Path) -> None:
    """Different params should produce separate stub entries."""
    messages = [
        _make_request(1, "tool.alpha", {"x": 1}),
        _make_response(1, {"val": "a"}),
        _make_request(2, "tool.alpha", {"x": 2}),
        _make_response(2, {"val": "b"}),
    ]
    stub = generate_stub(messages)
    assert len(stub["methods"]["tool.alpha"]) == 2


def test_stub_server_serves_sequence_in_order(tmp_path: Path) -> None:
    """Stub server should return responses in recorded order."""
    from collections import defaultdict

    h = params_hash({"x": 1})
    stub = {
        "methods": {
            "tool.alpha": {
                h: [{"result": {"ok": True}}, {"result": {"ok": False}}],
            }
        },
        "fallback_rules": [],
    }
    counters: dict[str, int] = defaultdict(int)

    resp1 = _response_for_request(
        stub,
        method="tool.alpha",
        request_id=1,
        params={"x": 1},
        counters=counters,
        strict=False,
    )
    assert resp1["result"] == {"ok": True}

    resp2 = _response_for_request(
        stub,
        method="tool.alpha",
        request_id=2,
        params={"x": 1},
        counters=counters,
        strict=False,
    )
    assert resp2["result"] == {"ok": False}


def test_stub_server_non_strict_repeats_last(tmp_path: Path) -> None:
    """Non-strict: third call should repeat the last captured response."""
    from collections import defaultdict

    h = params_hash({"x": 1})
    stub = {
        "methods": {
            "tool.alpha": {h: [{"result": {"ok": True}}, {"result": {"ok": False}}]},
        },
        "fallback_rules": [],
    }
    counters: dict[str, int] = defaultdict(int)

    for _ in range(2):
        _response_for_request(
            stub,
            method="tool.alpha",
            request_id=1,
            params={"x": 1},
            counters=counters,
            strict=False,
        )
    resp3 = _response_for_request(
        stub,
        method="tool.alpha",
        request_id=3,
        params={"x": 1},
        counters=counters,
        strict=False,
    )
    assert resp3["result"] == {"ok": False}


def test_stub_server_strict_fails_on_excess_call(tmp_path: Path) -> None:
    """Strict: third call should return a sequence-exhausted error."""
    from collections import defaultdict

    h = params_hash({"x": 1})
    stub = {
        "methods": {
            "tool.alpha": {h: [{"result": {"ok": True}}]},
        },
        "fallback_rules": [],
    }
    counters: dict[str, int] = defaultdict(int)

    _response_for_request(
        stub,
        method="tool.alpha",
        request_id=1,
        params={"x": 1},
        counters=counters,
        strict=True,
    )
    resp2 = _response_for_request(
        stub,
        method="tool.alpha",
        request_id=2,
        params={"x": 1},
        counters=counters,
        strict=True,
    )
    assert "error" in resp2
    assert resp2["error"]["code"] == -32005


def test_roundtrip_sequence_stub(tmp_path: Path) -> None:
    """write_stub / load_stub should preserve sequence lists."""
    h = params_hash({"n": 0})
    stub_data = {
        "schema_version": "1",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "server_name": "test",
        "methods": {
            "tool.count": {h: [{"result": {"i": 0}}, {"result": {"i": 1}}]},
        },
        "fallback_rules": [],
    }
    path = tmp_path / "stub.json"
    write_stub(path, stub_data)
    loaded = load_stub(path)
    seq = loaded["methods"]["tool.count"][h]
    assert isinstance(seq, list)
    assert len(seq) == 2
