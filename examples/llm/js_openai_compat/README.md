# Capturing LLM Calls from JS/TS (and Other Non-Python Apps)

Python SDK capture (`flightlog sdk install-sitecustomize`) only works for Python processes. For JS/TS, Go, or any other language, use the **LLM proxy** and point your OpenAI-compatible client at it.

## How it works

```
Your JS/TS app  →  flightlog llm proxy  →  Real upstream (OpenAI/Anthropic/etc.)
                         ↓
                   pack/ (JSONL transcript)
```

## Quickstart

**1. Start the proxy** (in a separate terminal):

```bash
uv run flightlog llm proxy \
  --listen 127.0.0.1:4999 \
  --upstream https://api.openai.com \
  --out /tmp/fl-capture \
  --provider-family openai_compat
```

**2. Point your app at the proxy** by setting the base URL environment variable:

```bash
# OpenAI Node.js SDK
OPENAI_BASE_URL=http://127.0.0.1:4999 node your_app.js

# Or in code:
# const openai = new OpenAI({ baseURL: "http://127.0.0.1:4999" });
```

**3. Stop the proxy** (Ctrl-C). Transcripts land under `/tmp/fl-capture/`.

**4. Build a pack** from the captured transcript:

```bash
uv run flightlog pack build \
  --input /tmp/fl-capture/<session>.jsonl \
  --out /tmp/fl-pack
```

## Example Node.js snippet

```js
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1",
  apiKey: process.env.OPENAI_API_KEY,
});

const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello!" }],
});

console.log(response.choices[0].message.content);
```

Run it with:

```bash
OPENAI_BASE_URL=http://127.0.0.1:4999/v1 node snippet.js
```

## Limitations

- The proxy does **not** perform TLS interception. It only intercepts requests your app sends **directly** to the configured base URL.
- For HTTPS upstream, `httpx` (used internally) handles the TLS to the real upstream; the local proxy listen address is always plain HTTP.
- Streaming responses (SSE) are captured incrementally; the full content is stored in the transcript.

## See also

- [`examples/llm/openai_compat/`](../openai_compat/) — fixture-based OpenAI-compatible capture example
- [`examples/llm/gemini/`](../gemini/) — fixture-based Gemini capture example
- `flightlog llm proxy --help` for all options
