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
    SESSION_ID_HEADER: str = os.getenv("SESSION_ID_HEADER", "X-Session-ID")
    SESSION_AFFINITY_ENABLED: bool = str(os.getenv("SESSION_AFFINITY_ENABLED", "True")).lower() == "true"
    SESSION_TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS", "24"))

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

    # --- Output Style Configuration ---
    ENABLE_RESPONSE_NORMALIZATION: bool = os.getenv(
        "ENABLE_RESPONSE_NORMALIZATION", "True"
    ).lower() == "true"

    UNIVERSAL_STYLE_GUIDE: str = os.getenv(
        "UNIVERSAL_STYLE_GUIDE",
        (
            "OUTPUT STYLE RULES:\n"
            "- Never start with \"As an AI\", \"Certainly\", \"Sure\", \"Of course\", or similar phrases\n"
            "- Never say \"Here's the...\" or \"Let me...\" as an opener\n"
            "- Provide direct answers without apology or hedging\n"
            "- Use valid JSON when JSON is requested (no code fences, no text around it)\n"
            "- Code blocks should include language specification\n"
            "- Keep Markdown minimal and functional\n"
            "- Respond in the same language as the user's question"
        ),
    )

    # --- Context Management Configuration ---
    CONTEXT_MANAGEMENT_MODE: str = os.getenv(
        "CONTEXT_MANAGEMENT_MODE", "static"
    )  # static, dynamic, reservoir, adaptive

    # Static mode: keep last N messages verbatim
    CONTEXT_STATIC_RECENT_KEEP: int = int(os.getenv(
        "CONTEXT_STATIC_RECENT_KEEP", "10"
    ))

    # Dynamic mode: adjust based on usage vs target
    CONTEXT_DYNAMIC_UTILIZATION_TARGET: float = float(os.getenv(
        "CONTEXT_DYNAMIC_UTILIZATION_TARGET", "0.8"
    ))  # Target utilization (0.0-1.0)
    CONTEXT_DYNAMIC_MIN_UTILIZATION: float = float(os.getenv(
        "CONTEXT_DYNAMIC_MIN_UTILIZATION", "0.3"
    ))  # Below this, boost allowed
    CONTEXT_DYNAMIC_MAX_BOOST: float = float(os.getenv(
        "CONTEXT_DYNAMIC_MAX_BOOST", "1.5"
    ))  # Maximum boost factor

    # Reservoir mode: keep recent verbatim, summarize older
    CONTEXT_RESERVOIR_RECENT_KEEP: int = int(os.getenv(
        "CONTEXT_RESERVOIR_RECENT_KEEP", "15"
    ))  # Recent messages to keep verbatim
    CONTEXT_RESERVOIR_SUMMARY_BUDGET: int = int(os.getenv(
        "CONTEXT_RESERVOIR_SUMMARY_BUDGET", "400"
    ))  # Tokens for summary of older content

    # Extractive summarization
    SUMMARIZATION_MAX_TOKENS: int = int(os.getenv(
        "SUMMARIZATION_MAX_TOKENS", "200"
    ))  # Max tokens for each extractive summary

    # Adaptive mode: task-based allocation
    CONTEXT_TASK_AWARE_ENABLED: bool = os.getenv(
        "CONTEXT_TASK_AWARE_ENABLED", "False"
    ).lower() == "true"
    CONTEXT_TASK_DEFAULT: str = os.getenv(
        "CONTEXT_TASK_DEFAULT", "general"
    )  # Default task when detection fails

    @classmethod
    def get_api_key(cls, key_name: str) -> str:
        """Get an API key by its config name. Raises if missing."""
        value = getattr(cls, key_name, None) or os.getenv(key_name, "")
        if not value:
            raise ValueError(f"API key '{key_name}' is not set in environment variables.")
        return value


# Singleton-like module-level instance
settings = Settings()
