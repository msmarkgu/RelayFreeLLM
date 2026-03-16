# RelayLLMs

RelayLLMs is a robust and flexible backend service designed to route user prompts to various AI model providers. Built with FastAPI, it serves as a centralized gateway to interact with multiple Large Language Models (LLMs) including Cerebras, Gemini, Groq, and Mistral.

## Features

-   **Multi-Provider Support**: Seamlessly integrate with Cerebras, Google Gemini, Groq, and Mistral AI.
-   **Smart Dispatching**: efficient routing of requests to the specified model and provider.
-   **Async Processing**: Supports asynchronous model calls and testing to prevent blocking operations.
-   **Health Monitoring**: Built-in health check and statistics endpoints.
-   **Extensible Architecture**: Easy to add new providers and routers.

## Supported Providers

-   **Cerebras**
-   **Google Gemini**
-   **Groq**
-   **Mistral AI**

## Prerequisites

-   Python 3.8+
-   `pip` package manager

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd RelayLLMs
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

RelayLLMs uses environment variables for configuration. The easiest way to manage these is by creating a `.env` file in the project root.

1.  **Create a `.env` file:**
    ```bash
    cp .env.example .env (if available, or just create one)
    ```

2.  **Add your API keys:**
    ```env
    GEMINI_APIKEY=your_gemini_api_key
    GROQ_APIKEY=your_groq_api_key
    MISTRAL_APIKEY=your_mistral_api_key
    CEREBRAS_APIKEY=your_cerebras_api_key
    ```

## Usage

### Starting the Server

Run the FastAPI server using the following command from the root directory:

```bash
python -m src.server
```

The server will start on `http://0.0.0.0:8000`.

### API Endpoints

#### Health Check
-   **URL**: `/` or `/health`
-   **Method**: `GET`
-   **Response**: Status information.

#### Chat Completions (OpenAI-compatible)
-   **URL**: `/v1/chat/completions`
-   **Method**: `POST`
-   **Payload**:
    ```json
    {
        "model": "meta-model",
        "messages": [
            {"role": "user", "content": "Explain Quantum Computing."}
        ]
    }
    ```
-   **Response**: OpenAI-compatible JSON response.

#### List Models
-   **URL**: `/v1/models`
-   **Method**: `GET`
-   **Response**: List of available models including the virtual "meta-model".

#### Get Usage Statistics
-   **URL**: `/v1/usage`
-   **Method**: `GET`
-   **Response**: Aggregated token and request counts.

## Running Tests

To run the full test suite, execute the test runner from the root directory:

```bash
python run_tests.py
```

This will discover and run all tests located in the `tests/` directory.

## Project Structure

```
RelayLLMs/
├── run_tests.py          # Test runner script
├── requirements.txt      # Python dependencies
├── src/                  # Source code
│   ├── server.py         # Entry point for the application
│   ├── router.py         # API route definitions
```

## Troubleshooting

### ModuleNotFoundError: No module named 'fastapi'
If you encounter this error, it means the dependencies are not installed in your current active Python environment.
1.  Ensure you have activated the correct environment (e.g., `conda activate py3.12` or `source venv/bin/activate`).
2.  Run `pip install -r requirements.txt`.

### ImportError: attempted relative import with no known parent package
Make sure you are running the server using the `-m` flag from the root directory:
```bash
python -m src.server
```
Don't try to run `python src/server.py` directly.

### Refresh Model Availability

As of 2026-03-15, the following models are available:

```bash
python -m tests.test_models_availability
```

==================================================
MODEL AVAILABILITY SUMMARY
==================================================
✅ PASS | Cerebras     | qwen-3-235b-a11b-instruct-2507           | Success
✅ PASS | Groq         | llama-3.3-70b-versatile                  | Success
✅ PASS | Groq         | qwen/qwen3-32b                           | Success
✅ PASS | Groq         | openai/gpt-oss-20b                       | Success
✅ PASS | Groq         | openai/gpt-oss-120b                      | Success
✅ PASS | Groq         | moonshotai/kimi-k2-instruct-0905         | Success
✅ PASS | Groq         | moonshotai/kimi-k2-instruct              | Success
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
TOTAL: 17/17 models available.
==================================================
