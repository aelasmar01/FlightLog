"""MCP stdio stub server."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from flightlog.mcp.stubgen import load_stub, params_hash


def _find_fallback(method: str, params: Any, stub: dict[str, Any]) -> dict[str, Any] | None:
    fallback_rules = stub.get("fallback_rules", [])
    if not isinstance(fallback_rules, list):
        return None

    params_text = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    for rule in fallback_rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("method") != method:
            continue
        pattern = rule.get("params_regex")
        if isinstance(pattern, str):
            import re

            if not re.search(pattern, params_text):
                continue
        response = rule.get("response")
        if isinstance(response, dict):
            return response
    return None


def _response_for_request(
    stub: dict[str, Any],
    *,
    method: str,
    request_id: str | int | None,
    params: Any,
    counters: dict[str, int],
    strict: bool,
) -> dict[str, Any]:
    methods = stub.get("methods", {})
    if not isinstance(methods, dict):
        methods = {}

    method_map = methods.get(method, {})
    request_hash = params_hash(params)
    counter_key = f"{method}:{request_hash}"

    if isinstance(method_map, dict) and request_hash in method_map:
        mapping = method_map[request_hash]

        # Support both legacy single-dict format and new list format.
        if isinstance(mapping, list):
            idx = counters[counter_key]
            if idx >= len(mapping):
                if strict:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32005,
                            "message": "Stub sequence exhausted (strict mode)",
                            "data": {
                                "method": method,
                                "params_hash": request_hash,
                                "call_index": idx,
                                "sequence_length": len(mapping),
                            },
                        },
                    }
                # Non-strict: replay last response indefinitely.
                idx = len(mapping) - 1
            entry = mapping[idx]
            counters[counter_key] += 1
        elif isinstance(mapping, dict):
            entry = mapping
        else:
            entry = {}

        if isinstance(entry, dict):
            response: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
            if "result" in entry:
                response["result"] = entry["result"]
            if "error" in entry:
                response["error"] = entry["error"]
            return response

    fallback = _find_fallback(method, params, stub)
    if fallback is not None:
        response = {"jsonrpc": "2.0", "id": request_id}
        response.update(fallback)
        return response

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32004,
            "message": "No stub mapping found for method+params",
            "data": {"method": method, "params_hash": request_hash},
        },
    }


def serve_stub(stub_path: Path, *, strict: bool = False) -> int:
    stub = load_stub(stub_path)
    counters: dict[str, int] = defaultdict(int)
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        method = payload.get("method")
        request_id = payload.get("id")
        if not isinstance(method, str):
            continue
        params = payload.get("params", {})
        response = _response_for_request(
            stub,
            method=method,
            request_id=request_id,
            params=params,
            counters=counters,
            strict=strict,
        )
        sys.stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=True) + "\n")
        sys.stdout.flush()
    return 0
