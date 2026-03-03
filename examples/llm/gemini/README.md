# Gemini Capture Example

Gemini proxy capture is represented through the shared `CaptureRecord` JSONL format.
This directory includes a sample capture file that can be packed without live network calls.

## Build and validate from capture-record JSONL

```bash
uv run flightlog pack build \
  --input examples/llm/gemini/sample_capture.jsonl \
  --out /tmp/flightlog-gemini-pack

uv run flightlog pack validate --path /tmp/flightlog-gemini-pack
```
