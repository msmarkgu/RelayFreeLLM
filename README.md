# RelayFreeLLM

> **One endpoint. More free AI than any single provider. Less rate limit headaches.**

Don't want to pay $$/month to use AI Models? RelayFreeLLM is an open-source gateway that combines **multiple free-tier providers** into a single OpenAI-compatible API — so you get aggregately more free inference with automatic failover.

```
# Your existing code works. Just change the URL.
client = OpenAI(base_url="http://localhost:8000/v1", api_key="fake")
```

**Gemini · Groq · Mistral · DeepSeek · NVIDIA · Cerebras · Cloudflare · Ollama**

No code changes. No retry logic. No 429 errors breaking your app.

It also speaks the **Anthropic Messages API**, so coding agents like **Claude Code** can run against the same local gateway with tool calling, streaming, and Claude-style model aliases.

---

## The Free Tier Problem → The RelayFreeLLM Solution

```
❌ Groq hits rate limit → Your app crashes       ✅ Gemini fails → Automatically tries Groq
❌ Gemini quota exhausted → User sees error       ✅ One provider down → Traffic routes to others
❌ Switching providers → Rewrite your integration  ✅ Same API for everyone → OpenAI-compatible
❌ Testing 5 providers → 5 different SDKs          ✅ More providers = More throughput
```

---

## What You Get

| Feature | Why It Matters |
|---------|----------------|
| **OpenAI-compatible** | Drop-in for your existing code. LangChain, LlamaIndex, any SDK. |
| **Anthropic-compatible** | `POST /v1/messages` and `POST /v1/messages/count_tokens` for Claude Code and other Anthropic clients. |
| **Agent tool calling** | OpenAI-style `tools`/`tool_choice` and Anthropic `tool_use`/`tool_result` blocks, with native passthrough on supported providers. |
| **Automatic Failover** | Provider down? One model hit limits? We try the next one automatically. Zero downtime. |
| **Session Affinity** | Pin conversations to a provider via `X-Session-ID` for context caching benefits. |
| **4-Mode Context Management** | Static, Dynamic, Reservoir, Adaptive — with extractive summarization to preserve long conversations. |
| **Consistent Output Style** | Universal style guidance + response normalizers eliminate provider-specific quirks. Opt out per-request via `X-Use-ServerSide-System-Prompt: false`. |
| **Intent-Based Routing** | `model_type=coding`, `model_scale=large`, `model_name=deepseek` — tell us what you need, not which API to call. |
| **[NEW] Image-aware Routing** | Upload images in chat; the dispatcher automatically routes to vision-capable models. Explicit text-only model pick? Falls back within the same provider, then any provider. |
| **Real-time Streaming** | Full SSE streaming from every backend provider. |
| **Chat UI** | Built-in web chat interface at [`/chat`](http://localhost:8000/chat) — streaming, conversation history, dark/light mode, Browser or Server storage. |
| **Local + Cloud** | Mix your private Ollama instance with cloud free tiers seamlessly. |
| **Admin Dashboard** | Visual editor for provider limits and real-time usage monitoring at [`/admin`](http://localhost:8000/admin) — no manual JSON editing or server restarts. |
| **Local-first security** | Binds to `127.0.0.1` by default, restricts CORS to localhost origins, and supports an optional bearer token via `RELAY_AUTH_TOKEN`. |
| **Honest errors & usage** | Real HTTP status codes, structured error envelopes, and estimated token counts on both non-streaming responses and the final SSE chunk. |

---

## Who It's For

| User | Use Case |
|------|----------|
| **Independent developers** | Ship AI features without a $$$/month API bill |
| **Students & hobbyists** | GPT-level AI, no credit card or phone number required |
| **Self-hosters** | Combine Ollama privacy with cloud capacity |
| **Researchers** | Batch queries across providers for higher throughput |
| **Coding-agent users** | Run Claude Code locally against free tiers via the Anthropic Messages API |

**Community:** 120+ GitHub stars, 10+ forks, 20+ models from 6 providers included. Active development — 70+ commits in 12 weeks.

---

## Quick Start

### 1. Install
```bash
git clone https://github.com/msmarkgu/RelayFreeLLM.git && cd RelayFreeLLM
pip install -r requirements.txt
```

### 2. Add free API keys
Create a `.env` file in the project root folder:
```bash
GEMINI_APIKEY=      # ai.google.dev
GROQ_APIKEY=        # console.groq.com
MISTRAL_APIKEY=     # console.mistral.ai
NVIDIA_APIKEY=      # build.nvidia.com
SAMBANOVA_APIKEY=   # cloud.sambanova.ai
```

### 2.1 Protect the gateway (optional, recommended for agent use)

Add a token to `.env` to require `Authorization: Bearer <token>` on all API and admin routes:

```bash
RELAY_AUTH_TOKEN=your-random-secret
```

Health checks (`/` and `/health`) stay public so launchers can poll readiness. The server binds to `127.0.0.1` by default and only allows CORS requests from `localhost`/`127.0.0.1`. When running in Docker, the image sets `HOST=0.0.0.0`; publish only to loopback (`-p 127.0.0.1:8000:8000`) to keep the gateway local.

### 3. Verify connectivity (optional but recommended)
```bash
python -m tests.test_models_availability
```

<details>
<summary>Click to see expected output (20/20 models available)</summary>

```
======================================================================
MODEL AVAILABILITY SUMMARY
======================================================================
✅ PASS | Cerebras        | zai-glm-4.7                                   | Success
✅ PASS | Cerebras        | gpt-oss-120b                                  | Success
✅ PASS | Cerebras        | gemma-4-31b                                   | Success
✅ PASS | Groq            | llama-3.3-70b-versatile                       | Success
✅ PASS | Groq            | qwen/qwen3.6-27b                              | Success
✅ PASS | Groq            | openai/gpt-oss-120b                           | Success
✅ PASS | Groq            | openai/gpt-oss-20b                            | Success
✅ PASS | Groq            | openai/gpt-oss-safeguard-20b                  | Success
✅ PASS | Groq            | groq/compound                                 | Success
✅ PASS | Mistral         | mistral-large-latest                          | Success
✅ PASS | Mistral         | mistral-medium-latest                         | Success
✅ PASS | Mistral         | codestral-latest                              | Success
✅ PASS | Mistral         | mistral-large-2512                            | Success
✅ PASS | Mistral         | mistral-medium-2508                           | Success
✅ PASS | Mistral         | mistral-medium-2505                           | Success
✅ PASS | Mistral         | mistral-medium                                | Success
✅ PASS | Mistral         | codestral-2508                                | Success
✅ PASS | Gemini          | gemini-2.5-flash                              | Success
✅ PASS | Nvidia          | minimaxai/minimax-m3                          | Success
✅ PASS | Nvidia          | stepfun-ai/step-3.7-flash                     | Success
======================================================================
TOTAL: 20/20 models available.
======================================================================
```

</details>

### 4. Start the server
```bash
python -m src.server
```

### 4.1 Run with Docker
Build and run the minimal Docker image from the project root:
```bash
docker build -t relayfreellm .
```

Run the container with your `.env` file mounted so API keys and provider config are available:
```bash
docker run --rm --env-file .env -p 8000:8000 relayfreellm
```

### 5. Open the Admin Dashboard
Once the server is running, open [`http://localhost:8000/admin`](http://localhost:8000/admin) in your browser to manage rate limits, add/remove models, and monitor usage in real time.

### 6. Open the Chat Interface
Open [`http://localhost:8000/chat`](http://localhost:8000/chat) to start chatting — streaming responses, persistent conversation history, dark/light mode, and direct access to all providers.

### 7. Use it
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="relay-free")
response = client.chat.completions.create(
    model="meta-model",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

Or route to a specific provider:
```python
response = client.chat.completions.create(
    model="groq/llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

---

## Admin Dashboard

Manage everything from your browser. The admin dashboard at [`http://localhost:8000/admin`](http://localhost:8000/admin) provides a visual interface for managing provider model limits and viewing real-time usage statistics — no need to edit JSON files by hand or restart the server.

### Limits Tab

- **Providers** are displayed as collapsible cards, each showing its models in an editable table.
- **Edit any field inline**: model name, type (text/coding/image/etc.), scale (large/medium/small), max context length, and all 7 rate-limit values (requests/tokens per second/minute/hour/day).
- **Add/remove** models per provider, or add/remove entire providers.
- **Save** writes your changes to `provider_model_limits.json` and hot-reloads the rate-limit tracker — no server restart required.

### Usage Tab

- **Summary cards** show total requests, prompt tokens, completion tokens, and total tokens across all providers.
- **Per-provider breakdown** tables list each model's individual usage.
- **Reset Stats** zeros out all counters in `usage_stats.json` with a confirmation prompt.
- Data auto-refreshes every 30 seconds.

All data is stored in JSON files — no database required.

---

## Chat Interface

A full-featured web chat UI ships with the server at [`/chat`](http://localhost:8000/chat).

### Features

- **Streaming responses** — real-time token-by-token output
- **Provider attribution** — see which provider/model handled each response
- **Conversation history** — persist chats in your browser (`localStorage`) or on the server (opt-in)
- **Conversation management** — sidebar with search, rename, copy, delete
- **Edit & delete messages** — fix typos or prune unwanted branches mid-conversation
- **Image upload** — file picker, paste, drag-and-drop; images rendered inline in message bubbles (click to expand)
- **Intent-based routing** — switch models via the dropdown (`meta-model` or specific `Provider/Model`)
- **Dark/light mode** — toggle in the header, preference saved

### Storage

By default, conversations are saved to your browser's `localStorage`. Switch to **Server** storage via the header dropdown to persist conversations to `conversations.json` on disk — survives browser resets and is accessible across devices sharing the same device ID.

---

## How Routing Works

### Intent-Based Selection
```json
{"model": "meta-model"}                              // Any provider, picks the next available
{"model": "meta-model", "model_type": "coding"}      // Any coding model
{"model": "meta-model", "model_scale": "large"}       // Only large models
{"model": "meta-model", "model_name": "deepseek"}     // Prefer DeepSeek models
{"model": "Gemini/gemini-2.5-flash"}                  // Specific provider/model
```

### Automatic Failover
```
Request → Groq (rate limited)
        → Circuit breaker activates (60s cooldown)
        → Retry → Gemini
        → Retry → Mistral
        → Success ✓
```

### Image-Aware Routing

When a user message contains `image_url` content parts (as defined by the OpenAI Chat Completions spec), the dispatcher automatically restricts model selection to vision-capable models:

- **Meta-model routing** — only models with `modality: "vision"` in the registry are considered during provider/model selection.
- **Specific routing** — if the user explicitly requests a text-only model (e.g. `nvidia/minimaxai/minimax-m2.7`), the dispatcher first searches for a vision model within the same provider (e.g. `nvidia/moonshotai/kimi-k2.6`), then falls back to any provider's vision model. If none are available, a clear error is returned.

This behavior is driven by the per-model `modality` field in `provider_model_limits.json`. Models without image support remain available for text-only requests.

### Consistent Output Style
Despite switching between providers, every response is homogenized:
- **Style directive injection** — universal guide added to every system prompt
- **Response normalization** — strips "As an AI...", "Certainly!", fixes JSON, standardizes markdown

The standard system prompt injection can be disabled per-request by sending the header `X-Use-ServerSide-System-Prompt: false`. See [Agent Framework Support](#agent-framework-support) below.

---

## Advanced Features

### Session Affinity
Pass `X-Session-ID: user-123` and the gateway pins that user to a single provider. If that provider fails, the session automatically migrates.

### Tool Calling

Chat Completions clients can send OpenAI-style tool definitions. Tool requests are routed only to providers that support native tool calling, and `tool_use`/`tool_result` pairs are kept intact instead of being summarised by the context manager.

```python
response = client.chat.completions.create(
    model="meta-model",
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }],
)

call = response.choices[0].message.tool_calls[0]
# Execute the tool client-side, then append the result and call again:
# {"role": "tool", "tool_call_id": call.id, "content": "18°C, cloudy"}
```

Streaming tool calls emit `delta.tool_calls` fragments plus a final chunk with `finish_reason: "tool_calls"`.

Providers with native tool passthrough: **Groq, Cerebras, NVIDIA, SambaNova, Ollama, DeepSeek, Cloudflare**. Gemini and Mistral can be used for text but are excluded from tool-enabled routing.

### Errors & Usage

Failures now return meaningful HTTP statuses (400/401/429/500/502) with an OpenAI-style envelope:

```json
{"error": {"message": "All retries failed...", "type": "upstream_error"}}
```

Streaming failures emit a final `data: {"error": {...}}` event instead of a fake `finish_reason: "error"`. Successful streams end with a usage chunk:

```json
{"usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46}}
```

Token counts are estimated locally (not provider-reported), but are always non-zero so harness context budgeting works.

### Agent Framework Support
Agent frameworks (LangChain, AutoGen, CrewAI) manage their own system prompt and conversation history. To prevent the gateway from injecting its standard prompt or reconstructing the message array, send the header:

```
X-Use-ServerSide-System-Prompt: false
```

Behaviour when `false` (either per-request header or server `settings.json` default):

- The client's `messages` array is forwarded verbatim, preserving message order and roles (including `assistant` messages with `tool_calls` and `tool` result messages).
- No server-side `STANDARD_SYSTEM_PROMPT` or style directive is injected.
- The client's own system message (if any) is used without augmentation.
- If the client sent no system message, no system message is sent to the provider.

Set the server-wide default in `settings.json`:
```json
{
  "routing": {
    "use_server_side_system_prompt": false
  }
}
```

> **Note:** For full client-order fidelity, pair this with `CONTEXT_MANAGEMENT_MODE=static` in `settings.json` — modes like `reservoir` and `adaptive` may still reorder or summarise context when the conversation exceeds the token budget.

### Multi-Turn Context Management
| Mode | Behavior |
|------|----------|
| **Static** | Keeps the last N messages verbatim. |
| **Dynamic** | Adjusts context window based on real-time token usage. |
| **Reservoir** | Recent messages verbatim + extractive summary of older history. |
| **Adaptive** | Detects coding vs chat conversations and switches strategy. |

The Reservoir mode uses a **TF-scoring algorithm** to identify the most informative sentences, applies position bias for topicality, and greedily selects segments to fit your token budget — no LLM calls needed.

---

## API Reference

All API and admin routes accept `Authorization: Bearer $RELAY_AUTH_TOKEN` when `RELAY_AUTH_TOKEN` is set. `/` and `/health` remain public.

### `POST /v1/chat/completions`
| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | `"meta-model"` for auto-routing, or `"provider/model"` for direct |
| `messages` | array | Standard OpenAI message format. `content` accepts `str` or `list[{type, text, ...}]` for multi-modal messages. |
| `stream` | bool | Enable SSE streaming |
| `model_type` | string | Filter: `text`, `coding`, `image`, `speech`, `embedding`, `moderation`, `ocr` |
| `model_scale` | string | Filter: `large`, `medium`, `small` |
| `model_name` | string | Match model name substring |
| `tools` | array | OpenAI-style function tool definitions. Restricts routing to tool-capable providers. |
| `tool_choice` | string or object | `"auto"`, `"required"`, or `{"type": "function", "function": {"name": "..."}}` |

### `POST /v1/messages` (Anthropic)

Accepts the Anthropic Messages request shape: `model`, `max_tokens`, `messages` with `text`/`image`/`tool_use`/`tool_result`/`thinking` content blocks, optional `system`, `tools`, `tool_choice`, `temperature`, and `stream`. Returns an Anthropic message object or Anthropic SSE events (`message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`, `error`).

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="relay-free",  # or RELAY_AUTH_TOKEN
)
message = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
```

Errors use the Anthropic envelope `{"type": "error", "error": {"type": "...", "message": "..."}}`.

### `POST /v1/messages/count_tokens`

Estimates input tokens for an Anthropic Messages request and returns `{"input_tokens": N}`.

### `GET /v1/models`
```bash
curl http://localhost:8000/v1/models?type=coding&scale=large
```

Requests carrying an `anthropic-version` header receive the Claude tier aliases instead of the raw provider catalog.

> **Multi-modal content:** The `content` field in each message accepts either a plain string or a list of content parts (e.g. `[{"type": "text", "text": "..."}, {"type": "image_url", "url": "..."}]`), matching the OpenAI Chat Completions spec. When image parts are present, the dispatcher automatically routes to vision-capable models only (see [Image-Aware Routing](#image-aware-routing)). Text parts are flattened before being sent to providers that don't support structured content.
>
> **Agent frameworks:** To send the client's `messages` array verbatim without server-side system prompt injection, set `X-Use-ServerSide-System-Prompt: false`. See [Agent Framework Support](#agent-framework-support).

### `GET /v1/usage`
```bash
curl http://localhost:8000/v1/usage
```

### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin` | Admin dashboard UI |
| `GET` | `/admin/api/limits` | Get current provider model limits |
| `PUT` | `/admin/api/limits` | Update and persist limits (hot-reloaded immediately) |
| `GET` | `/admin/api/usage` | Get usage statistics |
| `POST` | `/admin/api/usage/reset` | Reset usage stats to zero |

---

## Tutorial: Build a Free AI CLI

**`chat.py`** — A terminal chatbot that uses RelayFreeLLM with session persistence:
```python
from openai import OpenAI
import readline

client = OpenAI(base_url="http://localhost:8000/v1", api_key="relay-free")
history = []

while True:
    user = input("\n> ")
    history.append({"role": "user", "content": user})
    r = client.chat.completions.create(model="meta-model", messages=history)
    reply = r.choices[0].message.content
    print(reply)
    history.append({"role": "assistant", "content": reply})
```

Run it. No API bill. No rate limits. That's the point.

**`vision.py`** — Send an image; the dispatcher automatically routes to a vision-capable model:
```python
import base64
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="relay-free")

with open("photo.jpg", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

response = client.chat.completions.create(
    model="meta-model",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What's in this image?"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]
    }]
)
print(response.choices[0].message.content)
```

Run both. No API bill. No rate limits.

---

## Provider Model Limits (Optional)

Default rate limits in [`provider_model_limits.json`](src/provider_model_limits.json) work for most use cases. If you hit provider caps, adjust the limits for your account tier — either by editing the file directly or using the **Admin Dashboard** (`http://localhost:8000/admin`):

<details>
<summary>Click to see example with all fields</summary>

```json
{
  "providers": [
    {
      "name": "Groq",
      "models": [
        {
          "name": "llama-3.3-70b-versatile",
          "type": "text",
          "scale": "large",
          "limits": {
            "requests_per_second": 1,
            "requests_per_minute": 30,
            "requests_per_hour": 1800,
            "requests_per_day": 1000,
            "tokens_per_minute": 12000,
            "tokens_per_hour": 30000,
            "tokens_per_day": 100000
          },
          "Max_Context_Length": 131000,
          "modality": "text"
        },
        {
          "name": "meta-llama/llama-4-scout-17b-16e-instruct",
          "type": "text",
          "scale": "large",
          "limits": {
            "requests_per_second": 1,
            "requests_per_minute": 30,
            "requests_per_hour": 1800,
            "requests_per_day": 1000,
            "tokens_per_minute": 12000,
            "tokens_per_hour": 30000,
            "tokens_per_day": 100000
          },
          "Max_Context_Length": 128000,
          "modality": "vision"
        }
      ]
    }
  ]
}
```

</details>

---

## Architecture

<details>
<summary>Click to expand</summary>

```
        ┌─────────────────────────────────────────────────┐
        │                 Your Application                │
        └─────────────────────┬───────────────────────────┘
                              │ OpenAI-compatible API
        ┌─────────────────────▼───────────────────────────┐
        │              RelayFreeLLM Gateway               │
        │  ┌───────────┐    ┌───────────┐    ┌──────────┐ │
        │  │  Router   │───▶│Dispatcher │───▶│ContextMgr│ │
        │  │ /v1/chat  │    │ (Retries) │    │(Summary) │ │
        │  └───────────┘    └─────┬─────┘    └──────────┘ │
        │                         │          ┌──────────┐ │
        │                         └─────────▶│Affinity  │ │
        │                                    │  Map     │ │
        │                                    └──────────┘ │
        └─────────────────────────┬───────────────────────┘
                                  │
      ┌──────────┬──────────┬─────┴────┬──────────┬──────────┬──────────┐
      ▼          ▼          ▼          ▼          ▼          ▼          ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
 │ Gemini │ │  Groq  │ │ Mistral│ │Cerebras│ │DeepSeek│ │ Ollama │ │ NVIDIA │
 └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

</details>

---

## Using Claude Code

RelayFreeLLM can act as a local Anthropic backend for Claude Code. The gateway exposes `/v1/messages`, `/v1/messages/count_tokens`, and a Claude-projected `/v1/models`, so no external Anthropic account is needed.

### One-command launcher

```bash
python -m pip install -r requirements.txt
./scripts/relay-claude
```

The launcher:

- starts the gateway on `127.0.0.1:8000` if `/health` is not reachable (logs go to `relay-server.log`, override with `RELAY_LOG_FILE`);
- generates a random session bearer token unless `RELAY_AUTH_TOKEN` is already set;
- scrubs inherited `ANTHROPIC_*` variables, then sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, and `ANTHROPIC_MODEL` (default `claude-sonnet-5-5`);
- sets Claude Code flags for managed-provider mode, gateway model discovery, a 32k auto-compact window, and disables client watchdogs/timeouts so the gateway owns retries;
- runs `claude` with any extra arguments you pass (e.g. `./scripts/relay-claude --resume`).

If the gateway is **already running**, set `RELAY_AUTH_TOKEN` to the token that server was started with; otherwise the launcher's generated token will not be accepted.

Windows: start the server separately (`python -m src.server`), set `RELAY_AUTH_TOKEN` for both processes, then run `scripts\relay-claude.cmd`.

### Configure Claude Code manually

If you prefer to set the environment yourself:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8000
export ANTHROPIC_AUTH_TOKEN="$RELAY_AUTH_TOKEN"
export ANTHROPIC_MODEL=claude-sonnet-5-5
claude
```

### Model aliases

| Alias | Default backend |
|-------|-----------------|
| `claude-fable-5-2` | `groq/qwen/qwen3.8-27b` |
| `claude-opus-5-5` | `groq/openai/gpt-oss-120b` |
| `claude-sonnet-5-5` | `groq/qwen/qwen3.6-27b` |
| `claude-haiku-5-5` | `nvidia/minimaxai/minimax-m3` |

Override the mapping in `settings.json` under `claude.model_map`. Values are `provider/model` pairs; only tool-capable providers are considered when the request includes tools.

### Behaviour & limitations

- The adapter forces `X-Use-ServerSide-System-Prompt: false` internally, so Claude's own system prompt and tool-result history are forwarded verbatim. The separate `/v1/agents/run` Map–Reduce API is untouched.
- Streaming produces standard Anthropic SSE events; streamed tool arguments are buffered per `tool_use` block before emission.
- Thinking/reasoning from backend models is emitted as plain text, not signed Anthropic `thinking` blocks.
- Tool loops work only with providers that have native tool passthrough (Groq, Cerebras, NVIDIA, SambaNova, Ollama, DeepSeek, Cloudflare). Free-tier tool-calling reliability varies by model — test a chosen alias before long agent runs.
- Token counts are estimates, not provider-reported usage.

---

## Roadmap

- [x] Web dashboard for live provider status
- [x] Image upload routing (vision models)
- [x] Anthropic Messages API + Claude Code launcher
- [x] Native tool calling with capability-aware routing
- [x] Optional bearer auth, loopback bind, localhost-only CORS
- [x] HTTP error envelopes and streaming usage chunks
- [ ] Persistent rate limit state (survives restarts)
- [ ] Prompt caching layer
- [ ] Signed Anthropic thinking blocks
- [ ] Gemini/Mistral native tool passthrough
- [ ] Embeddings & image generation routing
- [ ] One-command Docker deploy

---

## Contributing

Found a new free provider? Adding one takes ~50 lines:

```python
# src/api_clients/my_provider_client.py
class MyProviderClient(ApiInterface):
    PROVIDER_NAME = "myprovider"

    async def call_model_api(self, request, stream):
        # Your API logic here
        pass
```

PRs welcome.

---

## Acknowledgements

Built with [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/), [httpx](https://www.python-httpx.org/), and AI coding tools.

Powered by the generous free tiers of [Google Gemini](https://ai.google.dev/), [Groq](https://groq.com/), [Mistral AI](https://mistral.ai/), [Cerebras](https://cerebras.ai/), [NVIDIA](https://build.nvidia.com/), [DeepSeek](https://deepseek.com/), [Cloudflare](https://cloudflare.com/), and [Ollama](https://ollama.com/).

---

*Built for developers who want great AI without the bill.*
