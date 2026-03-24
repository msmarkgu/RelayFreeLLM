"""
Model metadata detection utilities.

Auto-detect model type (text/coding/image/speech) and scale (large/medium/small)
based on naming heuristics and known model characteristics.
"""

TYPE_KEYWORDS = {
    "coding": [
        "codestral",
        "codellama",
        "code-",
        "deepseek-coder",
        "starcoder",
        "devstral",
        "codegemma",
        "-code",
    ],
    "image": [
        "vision",
        "pixtral",
        "image",
        "dall-e",
        "stable-diffusion",
        "imagen",
        "-img",
    ],
    "speech": ["whisper", "tts", "stt", "speech", "voxtral", "orpheus", "audio"],
    "embedding": ["embed", "embedding"],
    "moderation": ["moderation", "guard", "safeguard", "prompt-guard"],
    "ocr": ["ocr"],
}

SCALE_PARAMS = {
    "large": lambda p: p >= 70,
    "medium": lambda p: 20 <= p < 70,
    "small": lambda p: p < 20,
}

KNOWN_MODEL_PARAMS = {
    "llama-3.3-70b-versatile": 70,
    "llama-3.1-8b-instant": 8,
    "llama-3.1-8b": 8,
    "llama-3-70b": 70,
    "llama-3-8b": 8,
    "llama-4-scout-17b-16e-instruct": 17,
    "gpt-oss-120b": 120,
    "gpt-oss-20b": 20,
    "qwen-3-235b-a22b-instruct-2507": 235,
    "qwen/qwen3-32b": 32,
    "qwen3-32b": 32,
    "mistral-large-latest": 123,
    "mistral-large-2512": 123,
    "mistral-large-2-1-24-11": 123,
    "mistral-medium-latest": 70,
    "mistral-medium-2508": 70,
    "mistral-medium": 70,
    "mistral-small-2503": 24,
    "mistral-small": 24,
    "codestral-latest": 22,
    "codestral-2508": 22,
    "codestral": 22,
    "mistral-nemo-12b-24-07": 12,
    "ministral-3b-2410": 3,
    "ministral-8b-2410": 8,
    "devstral-medium-2505": 24,
    "devstral-small-2505": 22,
    "gemini-2.5-flash": 32,
    "gemini-2.5-pro": 200,
    "gemini-1.5-pro": 200,
    "gemini-1.5-flash": 32,
    "gemini-2.0-flash": 32,
    "gemma-2-27b": 27,
    "gemma-2-9b": 9,
    "deepseek-r1": 671,
    "deepseek-v3": 671,
    "deepseek-chat": 671,
    "moonshotai/kimi-k2-instruct-0905": 70,
    "moonshotai/kimi-k2-instruct": 70,
    "groq/compound": 120,
    "zai-glm-4.7": 355,
}


def detect_model_type(model_name: str) -> str:
    """
    Detect model type based on naming heuristics.

    Args:
        model_name: The model identifier (e.g., "codestral-latest", "llama-3.3-70b")

    Returns:
        One of: "text", "coding", "image", "speech", "embedding", "moderation", "ocr"
    """
    name_lower = model_name.lower()

    for model_type, keywords in TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return model_type

    return "text"


def detect_model_scale(model_name: str) -> str:
    """
    Detect model scale based on parameter count.

    Uses known model data first, then falls back to extracting
    parameter count from the model name (e.g., "70b", "8b").

    Args:
        model_name: The model identifier

    Returns:
        One of: "large", "medium", "small"
    """
    name_lower = model_name.lower()

    if model_name in KNOWN_MODEL_PARAMS:
        params = KNOWN_MODEL_PARAMS[model_name]
    else:
        import re

        match = re.search(r"(\d+)b", name_lower)
        if match:
            params = int(match.group(1))
        else:
            if "large" in name_lower:
                params = 100
            elif "medium" in name_lower:
                params = 35
            elif "small" in name_lower or "mini" in name_lower or "flash" in name_lower:
                params = 15
            else:
                params = 30

    for scale, check_fn in SCALE_PARAMS.items():
        if check_fn(params):
            return scale

    return "medium"


def get_model_metadata(model_name: str) -> dict:
    """
    Get complete metadata for a model.

    Args:
        model_name: The model identifier

    Returns:
        Dictionary with 'type' and 'scale' keys
    """
    return {
        "type": detect_model_type(model_name),
        "scale": detect_model_scale(model_name),
    }
