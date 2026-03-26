"""
Centralized configuration for RelayFreeLLM.

All settings are loaded from environment variables (with .env file support).
This replaces the old api_keys.json approach and scattered hardcoded values.
"""

import os
from dotenv import load_dotenv

# Load .env file from project root (if it exists)
_project_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))


class Settings:
    """Application settings loaded from environment variables."""

    # --- API Keys ---
    GEMINI_APIKEY: str = os.getenv("GEMINI_APIKEY", "")
    GROQ_APIKEY: str = os.getenv("GROQ_APIKEY", "")
    MISTRAL_APIKEY: str = os.getenv("MISTRAL_APIKEY", "")
    CEREBRAS_APIKEY: str = os.getenv("CEREBRAS_APIKEY", "")
    DEEPSEEK_APIKEY: str = os.getenv("DEEPSEEK_APIKEY", "")
    CLOUDFLARE_API_TOKEN: str = os.getenv("CLOUDFLARE_API_TOKEN", "")
    CLOUDFLARE_ACCOUNT_ID: str = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # --- Model Defaults ---
    DEFAULT_TEMPERATURE: float = float(os.getenv("DEFAULT_TEMPERATURE", "0.8"))
    DEFAULT_MAX_TOKENS: int = int(os.getenv("DEFAULT_MAX_TOKENS", "4000"))
    META_MODEL_NAME: str = os.getenv("META_MODEL_NAME", "meta-model")

    # --- Selection ---
    PROVIDER_STRATEGY: str = os.getenv("PROVIDER_STRATEGY", "roundrobin")
    MODEL_STRATEGY: str = os.getenv("MODEL_STRATEGY", "roundrobin")
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    WAIT_FOR_QUOTA: bool = os.getenv("WAIT_FOR_QUOTA", "True").lower() == "true"
    MAX_QUOTA_WAIT: int = int(os.getenv("MAX_QUOTA_WAIT", "3600"))  # 1 hour

    # --- Paths ---
    REGISTRY_FILE: str = os.getenv(
        "REGISTRY_FILE",
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "provider_model_limits.json"),
    )

    # --- Default System Prompt ---
    STANDARD_SYSTEM_PROMPT: str = os.getenv(
        "STANDARD_SYSTEM_PROMPT",
        (
            "IMPORTANT: You are a helpful, professional, and consistent AI assistant.\n"
            "1. **Tone**: Maintain a neutral, professional, and concise tone.\n"
            "2. **Format**: ALWAYS use Markdown formatting. Use headers for structure, "
            "bullet points for lists, and code blocks for code.\n"
            "3. **Clarity**: Avoid unnecessary fluff. Get straight to the point.\n"
            "4. **Language**: Respond in the same language as the user's prompt "
            "unless instructed otherwise."
        ),
    )

    @classmethod
    def get_api_key(cls, key_name: str) -> str:
        """Get an API key by its config name. Raises if missing."""
        value = getattr(cls, key_name, None) or os.getenv(key_name, "")
        if not value:
            raise ValueError(f"API key '{key_name}' is not set in environment variables.")
        return value


# Singleton-like module-level instance
settings = Settings()
