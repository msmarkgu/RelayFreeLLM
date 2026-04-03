"""
Response Normalization — standardizes outputs across different LLM providers.

Addresses the issue where different models produce inconsistent:
- Writing tones and styles
- Use of preamble/hedging
- Markdown/code formatting
"""

import json
import re
from typing import Optional


class ResponseNormalizer:
    PREAMBLE_PATTERNS = [
        r"^(As an AI|As a large language model|As an AI assistant|As a helpful assistant)[:\s]*",
        r"^(Certainly!|Of course!|Sure!|Absolutely!|Sure thing!)[:\s]*",
        r"^(Here('s| is) what I[' ]?ll do)[:\s]*",
        r"^(I[' ]?ll )",
        r"^(Let me |I[' ]?ll )",
        r"^(I understand|I see that)[:\s]*",
    ]

    EMPTY_BLOCK_PATTERNS = [
        r"```\w*\n*```",
        r"^\s*```\s*$",
    ]

    def __init__(self, strict_json: bool = False):
        self.strict_json = strict_json

    def normalize(self, content: str, response_format: Optional[dict] = None) -> str:
        """
        Apply all normalization steps to produce consistent output.
        
        Args:
            content: Raw response from the LLM
            response_format: Optional format hints (e.g., {"type": "json_object"})
        """
        if not content:
            return content

        original = content

        content = self._remove_preamble(content)
        content = self._remove_empty_blocks(content)
        content = self._standardize_whitespace(content)

        if response_format and response_format.get("type") == "json_object":
            content = self._fix_json_response(content)
        else:
            content = self._standardize_markdown(content)

        if content != original:
            self._log_normalization(original, content)

        return content

    def _remove_preamble(self, content: str) -> str:
        """Strip common AI preamble phrases."""
        for pattern in self.PREAMBLE_PATTERNS:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE | re.MULTILINE)
        return content.strip()

    def _remove_empty_blocks(self, content: str) -> str:
        """Remove empty code blocks and markdown artifacts."""
        for pattern in self.EMPTY_BLOCK_PATTERNS:
            content = re.sub(pattern, "", content, flags=re.MULTILINE)
        return content

    def _standardize_whitespace(self, content: str) -> str:
        """Normalize whitespace while preserving code block structure."""
        lines = content.split("\n")
        cleaned = []
        prev_empty = False

        for line in lines:
            is_empty = not line.strip()
            if is_empty:
                if not prev_empty:
                    cleaned.append("")
                prev_empty = True
            else:
                cleaned.append(line.rstrip())
                prev_empty = False

        result = "\n".join(cleaned).strip()
        return result

    def _standardize_markdown(self, content: str) -> str:
        """Standardize markdown formatting."""
        content = content.strip()

        code_block_counts = len(re.findall(r"```", content))
        if code_block_counts % 2 != 0:
            content = content + "\n```"

        return content

    def _fix_json_response(self, content: str) -> str:
        """Attempt to fix malformed JSON responses."""
        content = content.strip()

        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = re.sub(r"^```\w*\n?", "", content)

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        try:
            json.loads(content)
            return content
        except json.JSONDecodeError:
            pass

        json_start = content.find("{")
        json_end = content.rfind("}")

        if json_start != -1 and json_end != -1 and json_start < json_end:
            potential = content[json_start:json_end + 1]
            try:
                json.loads(potential)
                return potential
            except json.JSONDecodeError:
                pass

        for fix_fn in [
            self._fix_unquoted_keys,
            self._fix_single_quotes,
            self._fix_trailing_commas,
            self._fix_comments,
        ]:
            fixed = fix_fn(content)
            try:
                json.loads(fixed)
                return fixed
            except json.JSONDecodeError:
                continue

        return content

    def _fix_unquoted_keys(self, text: str) -> str:
        """Fix JSON with unquoted keys."""
        return re.sub(r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)", r'\1"\2"\3', text)

    def _fix_single_quotes(self, text: str) -> str:
        """Replace single quotes with double quotes in JSON strings."""
        result = []
        i = 0
        while i < len(text):
            if text[i] == "'":
                if i == 0 or text[i - 1] in "{[,: ":
                    result.append('"')
                elif i + 1 < len(text) and text[i + 1] in "}],:":
                    result.append('"')
                else:
                    result.append('"')
            else:
                result.append(text[i])
            i += 1
        return "".join(result)

    def _fix_trailing_commas(self, text: str) -> str:
        """Remove trailing commas before } or ]."""
        return re.sub(r",(\s*[}\]])", r"\1", text)

    def _fix_comments(self, text: str) -> str:
        """Remove JavaScript-style comments from JSON."""
        text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return text

    def _looks_like_json(self, content: str) -> bool:
        """Heuristic to detect JSON-like content."""
        trimmed = content.strip()
        return trimmed.startswith("{") or trimmed.startswith("[")

    def _log_normalization(self, original: str, normalized: str) -> None:
        """Log normalization changes for debugging."""
        from .logging_util import ProjectLogger

        logger = ProjectLogger.get_logger(__name__)
        logger.debug(
            f"Response normalized: {len(original)} -> {len(normalized)} chars"
        )
