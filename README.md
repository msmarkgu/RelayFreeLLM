# 🚀 RelayFreeLLM

> **The Ultimate Zero-Cost AI Gateway.**
> Combine multiple free-tier LLM APIs into a single, high-availability meta-model.

RelayFreeLLM is a robust, production-ready gateway built for developers, hobbyists, and students who want to harness the power of state-of-the-art LLMs **without spending a dime**. It intelligently aggregates free-tier quotas from multiple providers, giving you a "meta-model" that is far more resilient and capable than any single free-tier API.

---

## 🔥 Key Features

### 1. 💰 Absolute Zero Cost
Built exclusively for the "Free Tier" economy. We've pre-integrated **[Gemini](https://ai.google.dev/)**, **[Groq](https://groq.com/)**, **[Mistral](https://mistral.ai/)**, and **[Cerebras](https://cerebras.ai/)** because they currently offer generous free-tier limits with low barriers to entry—getting started usually requires nothing more than an email address.

### 2. 🔌 Bring Your Own Providers
RelayFreeLLM is an open platform. While we ship with four defaults, the architecture is designed for easy extension. Want to add a local Ollama instance or another niche free API? Just drop in a new client and you're ready to go.

### 3. 🧠 Universal "Meta-Model" API
Talk to one endpoint; get the best model.
- **Auto-Routing**: The gateway automatically selects the best available provider based on your intent.
- **Smart Retries**: If Groq hits a rate limit, RelayFreeLLM instantly "relays" your request to Gemini or Mistral. You never see the 429 error unless all providers' limits have been reached.

### 4. 🎯 Intent-Based Selection
Don't settle for "blind" routing. Tell the gateway what you need:

*   **By Scale**: Request `large` for complex reasoning or `small` for speed.
    ```json
    {"model": "meta-model", "model_scale": "large", "messages": [...]}
    ```
*   **By Type**: Specify `coding`, `text`, or `ocr` for the best tool.
    ```json
    {"model": "meta-model", "model_type": "coding", "messages": [...]}
    ```
*   **By Provider**: Need a specific flavor? Just route to `groq/llama-3`.
    ```json
    {"model": "groq/llama-3", "messages": [...]}
    ```
*   **By Model Name**: Love a specific model? Just request `deepseek-v3` and the gateway will find a provider for you.
    ```json
    {"model": "meta-model", "model_name": "deepseek-v3", "messages": [...]}
    ```

### 5. ⚡ Real-Time Streaming (SSE)
Experience the speed. RelayFreeLLM now supports full OpenAI-compatible **Server-Sent Events (SSE)**, bringing token-by-token streaming to every provider in the stack.

---

## 🛠 Features

-   **OpenAI-Compatible**: Use your favorite OpenAI SDKs or tools (LangChain, AutoGPT) by simply changing the `base_url`.
-   **Granular Rate Limiting**: Intelligent tracking across seconds, minutes, hours, and days to prevent bans and maximize uptime.
-   **Circuit Breakers**: Automatically puts unreliable providers on "cooldown" to maintain system health.
-   **No Background Dependencies**: Lightweight Python/FastAPI app. No Redis or complex DB required.

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/msmarkgu/RelayFreeLLM.git
cd RelayFreeLLM
pip install -r requirements.txt
```

### 2. Setup your keys
Create a `.env` file with your free API keys:
```bash
GEMINI_APIKEY=your_key
GROQ_APIKEY=your_key
MISTRAL_APIKEY=your_key
CEREBRAS_APIKEY=your_key
```

### 3. Verify your keys (Optional)
Ensure the providers' APIs are reachable before starting the server:
```bash
python -m tests.test_models_availability
```

### 4. Run it
```bash
python -m src.server
```

### 5. Use it like OpenAI
```python
import openai

client = openai.OpenAI(base_url="http://localhost:8000/v1", api_key="relay-free")

response = client.chat.completions.create(
  messages=[
    {"role": "system", "content": "You are a rocket scientist Assistant."},
    {"role": "user", "content": "Hello!"},
    {"role": "user", "content": "How do I build a rocket?"}
  ],
  stream=True  # ⚡ New: Streaming support!
)

for chunk in response:
    print(chunk.choices[0].delta.content, end="")
```
### 6. Or use cURL
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer relay-free" \
     -d '{
       "model": "meta-model",
       "messages": [
         {"role": "system", "content": "You are a rocket scientist Assistant."},
         {"role": "user", "content": "How do I build a rocket?"}
       ],
       "stream": true
     }'
```

---

## 📂 Project Structure

```text
RelayFreeLLM/
├── src/
│   ├── api_clients/        # Provider-specific implementations
│   ├── models.py           # OpenAI-compatible Pydantic models
│   ├── model_selector.py   # Quota-aware routing logic
│   ├── model_dispatcher.py # Resilience & Retry engine
│   ├── router.py           # FastAPI endpoints (SSE support)
│   └── server.py           # App entry point
├── tests/                  # Unit and integration test suite
└── provider_model_limits.json # The "Brain": Quota & Capability registry
```

---

## 🤝 Contributing

RelayFreeLLM is built by the community for the community. If you found a new free provider or want to improve the routing logic, PRs are always welcome!

---

*Made with ❤️ for those who love AI but hate bills.*
