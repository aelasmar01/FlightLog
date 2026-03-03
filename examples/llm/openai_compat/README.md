# OpenAI-Compatible Capture Example

This example shows both capture paths:

1. Live capture with the local reverse proxy (`flightlog llm proxy`)
2. Fixture-based pack build from `sample_capture.jsonl`

## 1) Live capture via reverse proxy

Start the proxy in one terminal:

```bash
uv run flightlog llm proxy \
  --listen 127.0.0.1:4999 \
  --upstream https://api.openai.com \
  --provider-family openai_compat \
  --out /tmp/flightlog-openai-capture
```

Point your app/agent to `http://127.0.0.1:4999` as the base URL and send OpenAI-compatible requests.
The proxy writes capture records to:

```text
/tmp/flightlog-openai-capture/capture.jsonl
```

Build and validate a pack from captured traffic:

```bash
uv run flightlog pack build \
  --input /tmp/flightlog-openai-capture/capture.jsonl \
  --out /tmp/flightlog-openai-pack

uv run flightlog pack validate --path /tmp/flightlog-openai-pack
```

## 2) Fixture-based build (no network)

```bash
uv run flightlog pack build \
  --input examples/llm/openai_compat/sample_capture.jsonl \
  --out /tmp/flightlog-openai-fixture-pack

uv run flightlog pack validate --path /tmp/flightlog-openai-fixture-pack
```
