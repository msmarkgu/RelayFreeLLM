# RelayFreeLLM

> **One endpoint. More free AI than any single provider. Less rate limit headaches.**

Don't want to pay $$/month to use AI Models? RelayFreeLLM is an open-source gateway that combines **8 free-tier providers** into a single OpenAI-compatible API — so you get aggregately more free inference with automatic failover.

```
# Your existing code works. Just change the URL.
client = OpenAI(base_url="http://localhost:8000/v1", api_key="fake")
```

**Gemini · Groq · Mistral · DeepSeek · NVIDIA · Cerebras · Cloudflare · Ollama**

No code changes. No retry logic. No 429 errors breaking your app.

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
| **Automatic Failover** | Provider down? One model hit limits? We try the next one automatically. Zero downtime. |
| **Session Affinity** | Pin conversations to a provider via `X-Session-ID` for context caching benefits. |
| **4-Mode Context Management** | Static, Dynamic, Reservoir, Adaptive — with extractive summarization to preserve long conversations. |
| **Consistent Output Style** | Universal style guidance + response normalizers eliminate provider-specific quirks. |
| **Intent-Based Routing** | `model_type=coding`, `model_scale=large`, `model_name=deepseek` — tell us what you need, not which API to call. |
| **Real-time Streaming** | Full SSE streaming from every backend provider. |
| **Local + Cloud** | Mix your private Ollama instance with cloud free tiers seamlessly. |

---

## Who It's For

| User | Use Case |
|------|----------|
| **Independent developers** | Ship AI features without a $$$/month API bill |
| **Students & hobbyists** | GPT-level AI, no credit card or phone number required |
| **Self-hosters** | Combine Ollama privacy with cloud capacity |
| **Researchers** | Batch queries across providers for higher throughput |

**Community:** 75 GitHub stars, 7 forks, 8 providers supported. Active development — 38+ commits in 6 weeks.

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
```

### 3. Verify connectivity (optional but recommended)
```bash
python -m tests.test_models_availability
```

<details>
<summary>Click to see expected output (21/21 models available)</summary>

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
✅ PASS | Nvidia       | moonshotai/kimi-k2-instruct              | Success
✅ PASS | Nvidia       | z-ai/glm4.7                              | Success
✅ PASS | Nvidia       | stepfun-ai/step-3.5-flash                | Success
✅ PASS | Nvidia       | google/gemma-3-27b-it                    | Success
✅ PASS | Nvidia       | qwen/qwen3-coder-480b-a35b-instruct      | Success
==================================================
TOTAL: 21/21 models available.
==================================================
```

</details>

### 4. Start the server
```bash
python -m src.server
```

### 4. Use it
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

## See It In Action

![RelayFreeLLM Demo](https://raw.githubusercontent.com/msmarkgu/RelayFreeLLM/main/relayfreellm-demo.gif)

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

### Consistent Output Style
Despite switching between providers, every response is homogenized:
- **Style directive injection** — universal guide added to every system prompt
- **Response normalization** — strips "As an AI...", "Certainly!", fixes JSON, standardizes markdown

---

## Advanced Features

### Session Affinity
Pass `X-Session-ID: user-123` and the gateway pins that user to a single provider. If that provider fails, the session automatically migrates.

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

### `POST /v1/chat/completions`
| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | `"meta-model"` for auto-routing, or `"provider/model"` for direct |
| `messages` | array | Standard OpenAI message format |
| `stream` | bool | Enable SSE streaming |
| `model_type` | string | Filter: `text`, `coding`, `ocr` |
| `model_scale` | string | Filter: `large`, `medium`, `small` |
| `model_name` | string | Match model name substring |

### `GET /v1/models`
```bash
curl http://localhost:8000/v1/models?type=coding&scale=large
```

### `GET /v1/usage`
```bash
curl http://localhost:8000/v1/usage
```

---

## Tutorial: Build a Free AI CLI in 3 Files

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

---

## Provider Model Limits (Optional)

Default rate limits in [`provider_model_limits.json`](src/provider_model_limits.json) work for most use cases. If you hit provider caps, edit the limits for your account tier:

```json
{
  "providers": [
    {
      "name": "Groq",
      "models": [
        {
          "name": "llama-3.3-70b-versatile",
          "limits": {
            "requests_per_minute": 30,
            "requests_per_hour": 1800,
            "tokens_per_minute": 12000
          },
          "max_context_length": 131072
        }
      ]
    }
  ]
}
```

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
      ┌──────────┬──────────┬─────┴────┬──────────┬──────────┐
      ▼          ▼          ▼          ▼          ▼          ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
 │ Gemini │ │  Groq  │ │ Mistral│ │Cerebras│ │DeepSeek│ │ Ollama │
 └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

</details>

---

## Roadmap

- [ ] Web dashboard for live provider status
- [ ] Persistent rate limit state (survives restarts)
- [ ] Prompt caching layer
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
