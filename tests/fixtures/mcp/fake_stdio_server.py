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
