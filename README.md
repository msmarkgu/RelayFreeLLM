# RelayFreeLLM

> **One endpoint. More free AI than any single provider. Less rate limit headaches.**

Don't want to pay $~$$$/month to use AI Models? RelayFreeLLM can help. It is an open-source gateway that combines free tier model providers like Gemini, Groq, Mistral, Cerebras, and Ollama into a single OpenAI-compatible API — so you get aggregately more free inference with automatic failover.

```
# Your existing code works. Just change the URL.
client = OpenAI(base_url="http://localhost:8000/v1", api_key="fake")
```

No code changes. No retry logic. No 429 errors breaking your app.


---

## Why You Need This

### The Free Tier Problem

Free AI APIs are useful — but using them directly can be painful:

```
❌ Groq hits rate limit → Your app crashes
❌ Gemini quota exhausted → User sees error
❌ Switching providers → Rewrite your integration
❌ Testing 5 providers → 5 different SDKs to manage
```

### The RelayFreeLLM Solution

```
✅ Gemini fails → Automatically tries Groq
✅ One provider down → Traffic routes to others
✅ Same API for everyone → OpenAI-compatible
✅ More providers = More throughput
```

You get a **meta-model**: a single endpoint that routes to the next available free provider, offers flexible context management, maintains session affinity, and fails over automatically to keep your app running.

---

## What You Get

| Feature | Why It Matters |
|---------|----------------|
| **OpenAI-compatible** | Drop-in for your existing code. LangChain, LlamaIndex, any SDK. |
| **Session Affinity** | Lock users to specific providers via `X-Session-ID`. Faster responses via provider-side context caching. |
| **Context Management** | 4 modes (Static, Dynamic, Reservoir, Adaptive). Smartly prunes long histories with multi-turn extractive summarization. |
| **Automatic Failover** | Provider down? One model hit limits? We try the next one automatically. Zero downtime. |
| **Consistent Output Style** | Universal style guidance and response normalizers eliminate provider-specific quirks. |
| **Strict Boot Validation** | Server verifies all models, registry entries, and API keys before binding to ensure a healthy gateway. |
| **Real-time Streaming** | Full SSE streaming support from every backend provider. |
| **Local models** | Seamlessly mix cloud free tiers with your private Ollama instance. |

---

## Who It's For

| User | Use Case |
|------|----------|
| **Independent developers** | Ship AI features without a $$$/month API bill |
| **Students & hobbyists** | GPT-level AI, no need credit card or phone number |
| **Self-hosters** | Combine Ollama privacy with cloud capacity |
| **Researchers** | Batch queries across providers for higher throughput |

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/msmarkgu/RelayFreeLLM.git
cd RelayFreeLLM
pip install -r requirements.txt
```

### 2. Add free API keys

Create a `.env` file:

```bash
# --- Providers (Required) ---
GEMINI_APIKEY=      # ai.google.dev
GROQ_APIKEY=        # console.groq.com
MISTRAL_APIKEY=     # console.mistral.ai
CEREBRAS_APIKEY=    # cloud.cerebras.ai

# --- Optional Providers ---
DEEPSEEK_APIKEY=
OLLAMA_BASE_URL=http://localhost:11434
```

**Note:** All other settings (context management, session affinity, HTTP timeout, etc.) are configured in `settings.json`.

### 3. Edit Model Limits (Optional)

Edit [`provider_model_limits.json`](src/provider_model_limits.json) to update rate limits for each model. Default values work for most use cases.

```json
{
  "providers": [
    {
      "name": "Groq",
      "models": [
        {
          "name": "llama-3.3-70b-versatile",
          "limits": {
            "requests_per_second": 1,
            "requests_per_minute": 30,
            "requests_per_hour": 1800,
            "requests_per_day": 1000,
            "tokens_per_minute": 12000,
            "tokens_per_hour": 30000,
            "tokens_per_day": 100000
          },
          "max_context_length": 131072
        }
      ]
    }
  ]
}
```

**Inferring limits:** Providers often only document some limits (e.g., only RPM and TPM). Infer the others:
- `requests_per_hour ≈ requests_per_minute × 60`
- `requests_per_day ≈ requests_per_hour × 24`
- Same pattern for token limits

| Provider | Documentation URL |
|----------|-------------------|
| Groq | https://console.groq.com/docs/models |
| Mistral | https://docs.mistral.ai/deployment/ai-studio/tier |
| Cerebras | https://inference-docs.cerebras.ai/support/rate-limits |
| Gemini | https://ai.google.dev/gemini-api/docs/rate-limits |
| DeepSeek | https://api-docs.deepseek.com/quick_start/rate_limit |

**Note:** Rate limits vary by account tier. Default values work for most use cases.

**Adding a new provider:** To add a new provider, create a new client in `src/api_clients/` and add its models/limits to this file. See existing providers for the JSON structure.

**Automation coming soon:** A CLI tool to auto-fetch / auto-refresh model limits from provider documentation is planned. This will make Step 3 fully automatic.

### 4. Verify connectivity (optional but recommended)
```bash
python -m tests.test_models_availability
```

Depending on your providers, the result should look like:

```
==================================================
MODEL AVAILABILITY SUMMARY
==================================================
✅ PASS | Cerebras     | qwen-3-235b-a22b-instruct-2507           | Success
✅ PASS | Groq         | llama-3.3-70b-versatile                  | Success
✅ PASS | Groq         | qwen/qwen3-32b                           | Success
✅ PASS | Groq         | openai/gpt-oss-20b                       | Success
✅ PASS | Groq         | openai/gpt-oss-120b                      | Success
✅ PASS | Groq         | openai/gpt-oss-safeguard-20b             | Success
✅ PASS | Groq         | groq/compound                            | Success
✅ PASS | Mistral      | mistral-large-latest                     | Success
✅ PASS | Mistral      | mistral-medium-latest                    | Success
✅ PASS | Mistral      | codestral-latest                         | Success
✅ PASS | Mistral      | mistral-large-2512                       | Success
✅ PASS | Mistral      | mistral-medium-2508                      | Success
✅ PASS | Mistral      | mistral-medium-2505                      | Success
✅ PASS | Mistral      | mistral-medium                           | Success
✅ PASS | Mistral      | codestral-2508                           | Success
✅ PASS | Gemini       | gemini-2.5-flash                         | Success
==================================================
TOTAL: 16/16 models available.
==================================================
```

### 5. Start the Server

```bash
python -m src.server
```

In console should see something like:

```
INFO:     Started server process [203452]
INFO:     Waiting for application startup.
...
...
...
2026-04-01 19:44:04,123 - src.model_selector - INFO - Provider sequence: ['Cerebras', 'Groq', 'Mistral', 'Gemini', 'Ollama'], Provider Strategy: roundrobin, Model Strategy: roundrobin
2026-04-01 19:44:04,123 - __main__ - INFO - Meta model 'meta-model' ready with providers: ['Cerebras', 'Cloudflare', 'Gemini', 'Groq', 'Mistral', 'Ollama']
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

```

### 6. Use it

**Python SDK:**
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="relay-free"
)

# Automatic routing - picks the next available free provider
response = client.chat.completions.create(
    model="meta-model",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Or route to specific provider
response = client.chat.completions.create(
    model="groq/llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

**Note on Consistent Output**: Regardless of which provider (Gemini, Groq, Mistral, etc.) handles your request, RelayFreeLLM ensures consistent output style through universal style guidance and response normalization. This means no jarring changes in tone or formatting when the system automatically fails over between providers.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer relay-free" \
  -H "Content-Type: application/json" \
  -d '{"model": "meta-model", "messages": [{"role": "user", "content": "Hi"}]}'
```

**LangChain:**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="relay-free",
    model="meta-model"
)
```

**REST Client Example** (using [VS Code REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension)
```
POST http://localhost:8000/v1/chat/completions HTTP/1.1
content-type: application/json

{
    "model": "meta-model",
    "messages": [
        {"role": "system", "content": "Format response in JSON."},
        {"role": "user", "content": "When was the country Romania founded?"}
    ]
}

### Specific Model Routing
# Directly target a specific provider and model
POST http://localhost:8000/v1/chat/completions HTTP/1.1
content-type: application/json

{
    "model": "Mistral/mistral-large-latest",
    "messages": [
        {"role": "user", "content": "What is the capital of France?"}
    ]
}

```

See more examples in [./tests/api.http](./tests/api.http).

---

## See It In Action

![RelayFreeLLM Demo](https://raw.githubusercontent.com/msmarkgu/RelayFreeLLM/main/relayfreellm-demo.gif)

---

## How Routing Works

### Intent-Based Selection

Tell RelayFreeLLM what you need:

```json
// "Any model from any providers, RelayFreeLLM will choose the next available"
{"model": "meta-model", "messages": [...]}

// "Give me coding model from any providers"
{"model": "meta-model", "model_type": "coding", "messages": [...]}

// "I prefer small models to run fast, give simple responses"
{"model": "meta-model", "model_scale": "small", "messages": [...]}

// "I want large models to do most capable reasoning"
{"model": "meta-model", "model_scale": "large", "messages": [...]}

// "I want DeepSeek models if available"
{"model": "meta-model", "model_name": "deepseek", "messages": [...]}

// "Specific provider/model"
{"model": "Gemini/gemini-2.5-flash", "messages": [...]}
```

### Automatic Failover

When a provider hits a rate limit:

```
Request → Groq (rate limited)
        → Circuit breaker activates
        → Retry → Gemini
        → Retry → Mistral
        → Success ✓
```

### Consistent Output Style

Despite automatic switching between providers, RelayFreeLLM maintains consistent output style:

- **Universal style guide** injected into every request's system prompt
- **Response normalization** removes provider-specific quirks
- **No jarring style switches** when failing over between providers
- **Consistent tone, formatting, and quality** regardless of backend

---

## Advanced Features

### Session Affinity (Conversation Caching)

In multi-turn conversations, many providers (like Gemini and Anthropic) offer **Context Caching** optimizations. To benefit from this, RelayFreeLLM supports Session Affinity.

By passing the `X-Session-ID` header, RelayFreeLLM will try to "pin" a user to the same provider for the duration of their session.

1. **User sends request** with `X-Session-ID: user-123`.
2. **Gateway routes** to Gemini and locks that session ID to Gemini.
3. **Subsequent requests** from `user-123` bypass the round-robin logic and go straight back to Gemini.
4. If Gemini fails or hit limits, the gateway automatically migrates the session to the next best provider and re-pins it.

### Multi-Turn Context Management

As conversations grow, they exceed free tier context limits. RelayFreeLLM's `ContextManager` uses advanced pruning to keep chats alive:

| Mode | Behavior |
|------|----------|
| **Static** | Keeps the last $N$ messages verbatim. Simplest but loses far context. |
| **Dynamic** | Uses real-time token tracking to boost the context window when usage is low, or contract it when usage spikes, ensuring you never exceed model context limits. |
| **Reservoir** | Keeps recent messages verbatim + adds an **extractive summary** of the older conversation. |
| **Adaptive** | Detects task type (e.g., coding vs chat) and switches between Reservoir and Static modes automatically. |

**Extractive Summarization**: Unlike simple truncation, Reservoir mode preserves the "essence" of your history. It uses a **TF-scoring algorithm** (Term Frequency) to identify sentences with the most unique information, applies a **position bias** for topicality, and greedily selects the highest-scoring segments to fit within your token budget.

```
Request → Gemini (adds "As an AI..." preamble)
        → Normalizer removes preamble
        → Clean, direct response returned

Request → Groq (adds "Sure thing!" opener)
        → Normalizer removes opener
        → Same clean, direct response style
```

---

## API Reference

### `POST /v1/chat/completions`

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | `"meta-model"` for auto-routing, or `"provider/model"` for direct |
| `messages` | array | Standard OpenAI message format |
| `stream` | bool | Enable SSE streaming (default: false) |
| `model_type` | string | Filter: `text`, `coding`, `ocr` |
| `model_scale` | string | Filter: `large`, `medium`, `small` |
| `model_name` | string | Match model name substring |

### `GET /v1/models`

List available models with status:

```bash
curl http://localhost:8000/v1/models?type=coding&scale=large
```

### `GET /v1/usage`

Track your aggregated usage:

```bash
curl http://localhost:8000/v1/usage
```

---

## Architecture

```
        ┌─────────────────────────────────────────────────┐
        │                 Your Application                │
        │         (OpenAI SDK, LangChain, etc.)           │
        └─────────────────────┬───────────────────────────┘
                              │ OpenAI-compatible API
                              │ (with optional X-Session-ID)
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
      ┌──────────┬──────────┬─────┴────┬──────────┬──────────┐
      ▼          ▼          ▼          ▼          ▼          ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
 │ Gemini │ │  Groq  │ │ Mistral│ │Cerebras│ │DeepSeek│ │ Ollama │
 └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

### Output Homogenization

To ensure consistent user experience despite provider switching:

1. **Style Directive Injection**: Universal style guide added to every request's system prompt
2. **Response Normalization**: Post-processing removes provider-specific quirks:
   - Strips AI preambles ("As an AI", "Certainly!", etc.)
   - Standardizes markdown and code formatting
   - Fixes and extracts JSON from code fences
   - Ensures consistent tone and formatting

This means users get the same high-quality, consistent output whether their request was handled by Gemini, Groq, Mistral, or any other provider.

---

## Project Structure

```
RelayFreeLLM/
├── src/
│   ├── server.py                 # Entry point
│   ├── router.py                 # API endpoints
│   ├── model_dispatcher.py       # Retry & circuit breaker logic
│   ├── model_selector.py         # Quota-aware routing
│   ├── provider_registry.py      # Auto-discovers providers
│   ├── models.py                 # Request/response models
│   └── api_clients/              # Provider implementations
│       ├── gemini_client.py
│       ├── groq_client.py
│       ├── mistral_client.py
│       └── ...
├── tests/                        # Unit & integration tests
└── provider_model_limits.json    # Rate limit configuration
```

---

## Roadmap

- [ ] Web dashboard for live provider status
- [ ] Persistent rate limit state
- [ ] Prompt caching layer
- [ ] Embeddings & image generation routing
- [ ] One-command Docker deploy

---

## Contributing

Found a new free provider? Adding one takes about 50 lines:

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

Powered by the generous free tiers of [Google Gemini](https://ai.google.dev/), [Groq](https://groq.com/), [Mistral AI](https://mistral.ai/), [Cerebras](https://cerebras.ai/), and [Ollama](https://ollama.com/).

---

*Built for developers who want great AI without the bill.*
