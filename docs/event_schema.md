# Model Event Payload Schema

FlightLog normalizes all provider traffic into a shared model-event contract.
`model.request` and `model.response` payloads use the same top-level key set.

## `model.request` payload keys

- `provider`: provider family (`anthropic`, `openai_compat`, `gemini`, etc.)
- `model`: model identifier (nullable)
- `messages`: normalized input messages in OpenAI message format
- `tool_calls`: normalized tool calls (`id`, `name`, `arguments_json`, `index`)
- `usage`: token usage object (`input_tokens`, `output_tokens`, `total_tokens`)
- `cost_usd`: numeric cost (nullable)
- `raw_request_ref`: optional artifact reference for raw request body
- `raw_response_ref`: optional artifact reference for raw response body
- `transport`: optional transport metadata (`url`, `status_code`, `latency_ms`, `streaming`, `attempt`, `request_id`)

## `model.response` payload keys

Includes all `model.request` keys, plus:

- `output_message`: normalized assistant output message in OpenAI message format

## Notes

- The structure is provider-agnostic; only values vary by provider.
- `raw_request_ref`/`raw_response_ref` are optional and can be `null`.
- Raw provider payloads should be stored as artifacts and referenced by these fields when available.
