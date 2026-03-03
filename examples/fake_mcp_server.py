"""Minimal stdio MCP echo server for examples and testing.

Reads JSON-RPC requests from stdin and writes responses to stdout.
Any method is accepted; the params are echoed back under "result.echo".

Usage:
    echo '{"jsonrpc":"2.0","id":1,"method":"tool.alpha","params":{"x":1}}' \\
      | python fake_mcp_server.py
"""

import json
import sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    payload = json.loads(line)
    if "method" not in payload:
        continue
    response = {
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "result": {"echo": payload.get("params", {})},
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()
