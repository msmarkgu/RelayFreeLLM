"""
Style configuration for consistent output across all LLM providers.

All providers use the same universal style guide for consistency.
"""

UNIVERSAL_STYLE_GUIDE = """OUTPUT STYLE RULES:
- Never start with "As an AI", "Certainly", "Sure", "Of course", or similar phrases
- Never say "Here's the..." or "Let me..." as an opener
- Provide direct answers without apology or hedging
- Use valid JSON when JSON is requested (no code fences, no text around it)
- Code blocks should include language specification
- Keep Markdown minimal and functional
- Respond in the same language as the user's question
"""


def get_style_directive(response_format=None):
    """
    Get the style directive for provider-agnostic consistent output.
    
    Args:
        response_format: Optional format hints (e.g., {"type": "json_object"})
    
    Returns:
        Combined style directive string
    """
    parts = [UNIVERSAL_STYLE_GUIDE]

    if response_format and response_format.get("type") == "json_object":
        parts.append("Return ONLY a valid JSON object. No markdown blocks, no explanation, no code fences.")

    return "\n\n".join(parts)
