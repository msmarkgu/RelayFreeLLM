# 🚀 RelayFreeLLM — Free LLM API Gateway & Load Balancer

> **Zero-cost, OpenAI-compatible LLM proxy.**
> Aggregate free-tier APIs from Gemini, Groq, Mistral, Cerebras & Ollama into one resilient endpoint.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-green)](https://fastapi.tiangolo.com)
[![OpenAI Compatible](https://img.shields.io/badge/OpenAI-compatible-orange)](https://platform.openai.com/docs/api-reference)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

**RelayFreeLLM** is an open-source **LLM gateway** and **load balancer** that unifies multiple free-tier AI APIs (Gemini, Groq, Mistral, Cerebras, Ollama, etc.) behind a single **OpenAI-compatible endpoint**. It intelligently routes requests, enforces rate limits, and automatically **retries on quota exhaustion**, giving you a "meta-model" far more resilient than any single free-tier API.

**No paid API keys. No Redis. No complex infrastructure.**

---

## 💡 Who Is This For?

- **Students & hobbyists** who want GPT-level AI without monthly bills
- **Indie developers** prototyping apps with LLM backends
- **AI agent builders** using LangChain, AutoGPT, or OpenAI SDK who need reliable, cost-free inference
- **Self-hosters** who want to combine a local **Ollama** instance with cloud free tiers for redundancy
- **Researchers** who need to batch queries across multiple providers to avoid rate limits

---

## 🔥 Key Features

### 1. 💰 Truly Free — No Credit Card Nor Phone Number Required
Built for the free-tier economy. Pre-integrated providers—**[Gemini](https://ai.google.dev/)**, **[Groq](https://groq.com/)**, **[Mistral](https://mistral.ai/)**, **[Cerebras](https://cerebras.ai/)**, and **local [Ollama](https://ollama.com/)**—as of March 2026, they offer generous free tiers, mostly requiring nothing more than an email address to get started. Note that some providers might change their policy and   require a phone number for verification in future. When that happens, you can simply remove them from the provider list and add new Providers.

### 2. 🔌 OpenAI-Compatible Drop-In Proxy
Point any OpenAI SDK, LangChain, LlamaIndex, AutoGPT, or cURL at `http://localhost:8000/v1` and it just works — **no code changes needed** in your existing AI apps.

### 3. ⚖️ Multi-Provider Load Balancing & Automatic Failover
Talk to one endpoint; get the best available model.
- **Smart Retries**: If Groq hits a rate limit (429), RelayFreeLLM instantly **relays** the request to Gemini or Mistral. Zero downtime.
- **Circuit Breakers**: Automatically quarantines unreliable providers to maintain system health.
- **Round-Robin & Random strategies**: Distribute load evenly or randomly across providers.

### 4. 🎯 Intent-Based Model Selection
Don't settle for blind routing. Tell the gateway what you need:

*   **By Scale**: Request `large` for complex reasoning tasks, `small` for fast cheap responses.
    ```json
    {"model": "meta-model", "model_scale": "large", "messages": [...]}
    ```
*   **By Type**: Pin to `coding`, `text`, or `ocr` specialization.
    ```json
    {"model": "meta-model", "model_type": "coding", "messages": [...]}
    ```
*   **By Provider**: Explicitly route to a specific provider and model.
    ```json
    {"model": "groq/llama-3", "messages": [...]}
    ```
*   **By Model Name**: Request a specific model family (e.g., DeepSeek, Llama, Gemma) and let the gateway find an available provider for it.
    ```json
    {"model": "meta-model", "model_name": "deepseek-v3", "messages": [...]}
    ```

### 5. ⚡ Real-Time Streaming (SSE)
Full **OpenAI-compatible Server-Sent Events (SSE)** streaming — token-by-token output from every provider.

### 6. 📊 Granular Rate Limit Management
Intelligent, in-memory quota tracking per provider and model across seconds, minutes, hours, and days — preventing bans and maximizing uptime without any external dependencies.

### 7. 🏠 Local AI Support — Ollama Integration
Combine **local Ollama models** (Llama 3, Mistral, Gemma, DeepSeek-R1, Qwen) with cloud free tiers for a fully private, zero-cost inference stack.

---

## 🛠 Full Feature List

| Feature | Details |
|---|---|
| **OpenAI API compatibility** | `/v1/chat/completions`, `/v1/models` |
| **Providers** | Gemini, Groq, Mistral, Cerebras, DeepSeek, Cloudflare AI, Ollama |
| **Models** | Llama 3, Gemini 2.5, Mistral Large, DeepSeek-V3/R1, Qwen, Codestral, and more |
| **Load balancing** | Round-robin and random strategies |
| **Automatic failover** | Retries on 429 / rate limit with next available provider |
| **Circuit breakers** | Auto-quarantine unreliable providers |
| **Quota tracking** | Per-model limits: RPS, RPM, RPH, RPD, TPM |
| **Streaming** | SSE (Server-Sent Events) — token streaming |
| **Self-hosted LLM** | Ollama integration for local models |
| **No infra deps** | Pure Python + FastAPI — no Redis, no database |

---

## 🚀 Quick Start

### 1. Install
```bash
git clone https://github.com/msmarkgu/RelayFreeLLM.git
cd RelayFreeLLM
pip install -r requirements.txt
```

### 2. Add your free API keys
Create a `.env` file — get these keys for free:
```bash
GEMINI_APIKEY=your_key      # https://aistudio.google.com/apikey
GROQ_APIKEY=your_key        # https://console.groq.com/keys
MISTRAL_APIKEY=your_key     # https://console.mistral.ai/
CEREBRAS_APIKEY=your_key    # https://cloud.cerebras.ai/
# Optional:
DEEPSEEK_APIKEY=your_key
CLOUDFLARE_API_TOKEN=your_token
CLOUDFLARE_ACCOUNT_ID=your_account_id
OLLAMA_BASE_URL=http://localhost:11434   # if you run Ollama locally
```

### 3. Verify connectivity (optional)
```bash
python -m tests.test_models_availability
```

### 4. Start the gateway
```bash
python -m src.server
```

### 5. Use with the OpenAI Python SDK
```python
import openai

# Just change base_url — no other code changes needed
client = openai.OpenAI(base_url="http://localhost:8000/v1", api_key="relay-free")

response = client.chat.completions.create(
  model="meta-model",  # or "groq/llama-3.3-70b-versatile", or "gemini/gemini-2.5-flash"
  messages=[
    {"role": "system", "content": "You are a helpful AI assistant."},
    {"role": "user", "content": "Explain quantum computing in simple terms."}
  ],
  stream=True  # ⚡ Streaming supported!
)

for chunk in response:
    print(chunk.choices[0].delta.content, end="")
```

### 6. Use with cURL
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer relay-free" \
     -d '{
       "model": "meta-model",
       "messages": [{"role": "user", "content": "Hello!"}],
       "stream": true
     }'
```

### 7. Use with LangChain
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="relay-free",
    model="meta-model"
)
response = llm.invoke("What is the capital of France?")
```

---

## 📡 API Reference

All endpoints are OpenAI-compatible and served under `http://localhost:8000`.

### `POST /v1/chat/completions`
The primary inference endpoint. Accepts the same request body as OpenAI's Chat Completions API, plus optional routing hints:

| Field | Type | Description |
|---|---|---|
| `model` | `string` | `"meta-model"` (auto-route), or `"provider/model"` for direct routing |
| `messages` | `array` | Standard OpenAI message array |
| `stream` | `bool` | Enable SSE streaming (default: `false`) |
| `model_type` | `string` | Filter by capability: `text`, `coding`, `ocr` |
| `model_scale` | `string` | Filter by size: `large`, `medium`, `small` |
| `model_name` | `string` | Route to a model matching this substring (e.g. `"deepseek"`, `"llama"`) |

### `GET /v1/models`
List all available provider models and their current status.

```bash
# All models
curl http://localhost:8000/v1/models

# Filter by type and scale
curl "http://localhost:8000/v1/models?type=coding&scale=medium"
```

Returns each model's `id`, `type`, `scale`, `status` (`available` / `cooldown`), and `cooldown_remaining_sec`.

### `GET /v1/usage`
Retrieve **aggregated token and request usage statistics** across all providers and models — useful for monitoring your free-tier consumption.

```bash
curl http://localhost:8000/v1/usage
```

Example response:
```json
{
  "total": {"prompt_tokens": 12400, "completion_tokens": 8300, "requests": 47},
  "providers": {
    "Gemini": {"requests": 20, "prompt_tokens": 5000, "completion_tokens": 3500},
    "Groq":   {"requests": 27, "prompt_tokens": 7400, "completion_tokens": 4800}
  }
}
```

---

## 📂 Project Structure

```text
RelayFreeLLM/
├── src/
│   ├── api_clients/        # Provider-specific clients (Gemini, Groq, Mistral, etc.)
│   ├── models.py           # OpenAI-compatible Pydantic request/response models
│   ├── model_selector.py   # Quota-aware routing & load balancing logic
│   ├── model_dispatcher.py # Resilience, retry, and circuit breaker engine
│   ├── router.py           # FastAPI endpoints with SSE streaming support
│   └── server.py           # Application entry point
├── tests/                  # Unit and integration test suite
└── src/provider_model_limits.json  # Provider quota & capability registry
```

---

## 🗺 Roadmap

- [ ] Web UI dashboard for live provider status and usage stats
- [ ] Persistent rate limit state (survive restarts)
- [ ] Prompt caching layer
- [ ] Support for embeddings and image generation routing
- [ ] Docker image / one-command deploy

---

## 🤝 Contributing

Found a new free provider? Want to improve routing logic? **PRs are welcome!**

Adding a new provider takes ~50 lines — just create a new client in `src/api_clients/` that extends `ApiInterface`.

---

## 🙏 Acknowledgements

RelayFreeLLM would not exist without the generosity of the free-tier AI community and the open-source ecosystem that powers it.

### Free-Tier Model Providers
A sincere thank-you to these companies for making world-class AI accessible to everyone — students, hobbyists, and indie developers — completely free of charge:

| Provider | What They Offer |
|---|---|
| **[Google Gemini](https://ai.google.dev/)** | Generous free tier for Gemini 2.5 Flash & Pro via Google AI Studio |
| **[Groq](https://groq.com/)** | Ultra-fast LPU inference, free tier for Llama, Qwen, DeepSeek models |
| **[Mistral AI](https://mistral.ai/)** | Free API access to Mistral and Codestral models |
| **[Cerebras](https://cerebras.ai/)** | High-speed inference on powerful open models, free tier available |
| **[DeepSeek](https://deepseek.com/)** | Frontier-quality open-weight models with a free API tier |
| **[Cloudflare AI](https://developers.cloudflare.com/workers-ai/)** | Edge-based model inference, generous free tier |
| **[Ollama](https://ollama.com/)** | Enabling anyone to run open-source LLMs locally, for free, forever |

### Open-Source Projects
This project is built on the shoulders of the open-source community, specifically but not limited to:

- **[FastAPI](https://fastapi.tiangolo.com/)** — The async Python web framework powering the gateway
- **[Pydantic](https://docs.pydantic.dev/)** — Data validation and OpenAI-compatible request/response modeling
- **[httpx](https://www.python-httpx.org/)** — Async HTTP client for provider communication
- **[OpenAI Python SDK](https://github.com/openai/openai-python)** — The de-facto standard API interface that makes this interoperable

---

## 🔍 Related Projects & Alternatives

> If you found this useful, you might also be interested in: LiteLLM · OpenRouter · LocalAI · Ollama · LM Studio · oobabooga

---

*Made with ❤️ for those who love Open Source and AI but hate bills.*
