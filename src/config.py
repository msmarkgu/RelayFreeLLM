"""
Centralized configuration for RelayFreeLLM.

All settings are loaded from environment variables (with .env file support).
This replaces the old api_keys.json approach and scattered hardcoded values.
"""

import json
import os
from dotenv import load_dotenv

# Load .env file from project root (if it exists)
_project_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))


class Settings:
    """Application settings using a layered loading approach (Defaults -> JSON -> ENV)."""

    def __init__(self):
        # 1. Set Defaults
        self._set_defaults()
        # 2. Layer JSON preferences
        self._load_from_json()
        # 3. Layer ENV overrides (Secrets & deployment specifics)
        self._load_from_env()

    def _set_defaults(self):
        # API Keys
        self.GEMINI_APIKEY = ""
        self.GROQ_APIKEY = ""
        self.MISTRAL_APIKEY = ""
        self.CEREBRAS_APIKEY = ""
        self.DEEPSEEK_APIKEY = ""
        self.CLOUDFLARE_API_TOKEN = ""
        self.CLOUDFLARE_ACCOUNT_ID = ""
        self.OLLAMA_BASE_URL = "http://localhost:11434"

        # Server
        self.HOST = "0.0.0.0"
        self.PORT = 8000
        self.LOG_LEVEL = "INFO"
        self.SESSION_ID_HEADER = "X-Session-ID"
        self.SESSION_AFFINITY_ENABLED = True
        self.SESSION_TTL_HOURS = 24
        self.SESSION_MAX_SESSIONS = 1000

        # Model Defaults
        self.DEFAULT_TEMPERATURE = 0.8
        self.DEFAULT_MAX_TOKENS = 4000
        self.META_MODEL_NAME = "meta-model"

        # Selection
        self.PROVIDER_STRATEGY = "roundrobin"
        self.MODEL_STRATEGY = "roundrobin"
        self.MAX_RETRIES = 3
        self.WAIT_FOR_QUOTA = True
        self.MAX_QUOTA_WAIT = 3600
        self.GLOBAL_PROVIDER_LOCK = False

        # Paths
        self.REGISTRY_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "provider_model_limits.json")
        self.SETTINGS_FILE = os.path.join(_project_root, "settings.json")

        # System Prompts
        self.STANDARD_SYSTEM_PROMPT = (
            "IMPORTANT: You are a helpful, professional, and consistent AI assistant.\n"
            "1. **Tone**: Maintain a neutral, professional, and concise tone.\n"
            "2. **Format**: ALWAYS use Markdown formatting. Use headers for structure, "
            "bullet points for lists, and code blocks for code.\n"
            "3. **Clarity**: Avoid unnecessary fluff. Get straight to the point.\n"
            "4. **Language**: Respond in the same language as the user's prompt "
            "unless instructed otherwise."
        )
        self.ENABLE_RESPONSE_NORMALIZATION = True
        self.UNIVERSAL_STYLE_GUIDE = (
            "OUTPUT STYLE RULES:\n"
            "- Never start with \"As an AI\", \"Certainly\", \"Sure\", \"Of course\", or similar phrases\n"
            "- Never say \"Here's the...\" or \"Let me...\" as an opener\n"
            "- Provide direct answers without apology or hedging\n"
            "- Use valid JSON when JSON is requested (no code fences, no text around it)\n"
            "- Code blocks should include language specification\n"
            "- Keep Markdown minimal and functional\n"
            "- Respond in the same language as the user's question"
        )

        # Context Management
        self.CONTEXT_MANAGEMENT_MODE = "static"
        self.CONTEXT_STATIC_RECENT_KEEP = 10
        self.CONTEXT_DYNAMIC_UTILIZATION_TARGET = 0.8
        self.CONTEXT_DYNAMIC_MIN_UTILIZATION = 0.3
        self.CONTEXT_DYNAMIC_MAX_BOOST = 1.5
        self.CONTEXT_RESERVOIR_RECENT_KEEP = 15
        self.CONTEXT_RESERVOIR_SUMMARY_BUDGET = 400
        self.SUMMARIZATION_MAX_TOKENS = 200
        self.CONTEXT_TASK_AWARE_ENABLED = False
        self.CONTEXT_TASK_DEFAULT = "general"

    def _load_from_json(self):
        """Overlay settings from settings.json."""
        if not os.path.exists(self.SETTINGS_FILE):
            return

        try:
            with open(self.SETTINGS_FILE, 'r') as f:
                data = json.load(f)

            mappings = {
                "session.affinity_enabled": "SESSION_AFFINITY_ENABLED",
                "session.id_header": "SESSION_ID_HEADER",
                "session.ttl_hours": "SESSION_TTL_HOURS",
                "session.max_sessions": "SESSION_MAX_SESSIONS",
                "context.management_mode": "CONTEXT_MANAGEMENT_MODE",
                "context.static_recent_keep": "CONTEXT_STATIC_RECENT_KEEP",
                "context.dynamic_utilization_target": "CONTEXT_DYNAMIC_UTILIZATION_TARGET",
                "context.dynamic_min_utilization": "CONTEXT_DYNAMIC_MIN_UTILIZATION",
                "context.dynamic_max_boost": "CONTEXT_DYNAMIC_MAX_BOOST",
                "context.reservoir_recent_keep": "CONTEXT_RESERVOIR_RECENT_KEEP",
                "context.reservoir_summary_budget": "CONTEXT_RESERVOIR_SUMMARY_BUDGET",
                "summarization.max_tokens": "SUMMARIZATION_MAX_TOKENS",
                "routing.global_provider_lock": "GLOBAL_PROVIDER_LOCK"
            }

            for json_path, attr_name in mappings.items():
                parts = json_path.split('.')
                val = data
                found = True
                for part in parts:
                    if isinstance(val, dict) and part in val:
                        val = val[part]
                    else:
                        found = False
                        break
                if found:
                    setattr(self, attr_name, val)
        except Exception as e:
            print(f"Warning: Failed to load settings.json: {e}")

    def _load_from_env(self):
        """Final overlay from Environment Variables."""
        # API Keys
        self.GEMINI_APIKEY = os.getenv("GEMINI_APIKEY", self.GEMINI_APIKEY)
        self.GROQ_APIKEY = os.getenv("GROQ_APIKEY", self.GROQ_APIKEY)
        self.MISTRAL_APIKEY = os.getenv("MISTRAL_APIKEY", self.MISTRAL_APIKEY)
        self.CEREBRAS_APIKEY = os.getenv("CEREBRAS_APIKEY", self.CEREBRAS_APIKEY)
        self.DEEPSEEK_APIKEY = os.getenv("DEEPSEEK_APIKEY", self.DEEPSEEK_APIKEY)
        self.OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", self.OLLAMA_BASE_URL)

        # Server
        self.HOST = os.getenv("HOST", self.HOST)
        self.PORT = int(os.getenv("PORT", str(self.PORT)))
        self.SESSION_AFFINITY_ENABLED = os.getenv("SESSION_AFFINITY_ENABLED", str(self.SESSION_AFFINITY_ENABLED)).lower() == "true"
        self.SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", str(self.SESSION_TTL_HOURS)))

        # Behavioral
        self.CONTEXT_MANAGEMENT_MODE = os.getenv("CONTEXT_MANAGEMENT_MODE", self.CONTEXT_MANAGEMENT_MODE)
        self.GLOBAL_PROVIDER_LOCK = os.getenv("GLOBAL_PROVIDER_LOCK", str(self.GLOBAL_PROVIDER_LOCK)).lower() == "true"

        # Paths
        self.REGISTRY_FILE = os.getenv("REGISTRY_FILE", self.REGISTRY_FILE)

    def get_api_key(self, key_name: str) -> str:
        """Get an API key by its config name."""
        value = getattr(self, key_name, "")
        if not value:
            raise ValueError(f"API key '{key_name}' is not set.")
        return value


# Singleton-like instance
settings = Settings()
