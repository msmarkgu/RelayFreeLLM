"""
Tests for ChatMessage and ChatCompletionRequest.

Covers the OpenAI-compatible content type (str | list of content parts)
introduced as the fix for Issue #5 / Problem 1.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pydantic import ValidationError

from src.models import ChatCompletionRequest, ChatMessage


class TestChatMessageStringContent(unittest.TestCase):
    """Plain string content must continue to work unchanged."""

    def test_string_content_accepted(self):
        msg = ChatMessage(role="user", content="hello")
        self.assertEqual(msg.content, "hello")

    def test_string_content_preserved_verbatim(self):
        msg = ChatMessage(role="assistant", content="  spaced  out  ")
        self.assertEqual(msg.content, "  spaced  out  ")

    def test_empty_string_content_allowed(self):
        msg = ChatMessage(role="user", content="")
        self.assertEqual(msg.content, "")


class TestChatMessageListContent(unittest.TestCase):
    """Content-parts lists (multi-modal) must be accepted per the OpenAI spec."""

    def test_single_text_part(self):
        msg = ChatMessage(
            role="user",
            content=[{"type": "text", "text": "Summarise this"}],
        )
        self.assertEqual(msg.content, [{"type": "text", "text": "Summarise this"}])

    def test_text_and_image_url_parts(self):
        parts = [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "url": "https://example.com/cat.png"},
        ]
        msg = ChatMessage(role="user", content=parts)
        self.assertEqual(msg.content, parts)

    def test_empty_list_content_allowed(self):
        msg = ChatMessage(role="user", content=[])
        self.assertEqual(msg.content, [])

    def test_extra_keys_in_part_are_preserved(self):
        # The model is intentionally permissive; we don't strip unknown keys.
        parts = [{"type": "text", "text": "hi", "extra": "ok"}]
        msg = ChatMessage(role="user", content=parts)
        self.assertEqual(msg.content, parts)


class TestChatMessageGetText(unittest.TestCase):
    """`get_text()` flattens content to a plain string."""

    def test_string_passthrough(self):
        self.assertEqual(
            ChatMessage(role="user", content="just a string").get_text(),
            "just a string",
        )

    def test_single_text_part(self):
        self.assertEqual(
            ChatMessage(
                role="user",
                content=[{"type": "text", "text": "Summarise this"}],
            ).get_text(),
            "Summarise this",
        )

    def test_text_and_image_url_concatenates_text_only(self):
        msg = ChatMessage(
            role="user",
            content=[
                {"type": "text", "text": "What is in this image?"},
                {"type": "image_url", "url": "https://example.com/cat.png"},
            ],
        )
        self.assertEqual(msg.get_text(), "What is in this image?")

    def test_multiple_text_parts_are_joined_with_space(self):
        msg = ChatMessage(
            role="user",
            content=[
                {"type": "text", "text": "Part one."},
                {"type": "text", "text": "Part two."},
            ],
        )
        self.assertEqual(msg.get_text(), "Part one. Part two.")

    def test_only_image_url_returns_empty_string(self):
        msg = ChatMessage(
            role="user",
            content=[{"type": "image_url", "url": "https://example.com/x.png"}],
        )
        self.assertEqual(msg.get_text(), "")

    def test_empty_list_returns_empty_string(self):
        self.assertEqual(ChatMessage(role="user", content=[]).get_text(), "")

    def test_mixed_text_and_unknown_types_skips_unknown(self):
        msg = ChatMessage(
            role="user",
            content=[
                {"type": "text", "text": "hello"},
                {"type": "audio_url", "url": "https://example.com/a.mp3"},
            ],
        )
        self.assertEqual(msg.get_text(), "hello")

    def test_non_dict_part_is_skipped(self):
        # Defensive: a malformed list (e.g. containing a string) should not
        # crash get_text(). It is skipped.
        msg = ChatMessage(
            role="user",
            content=["not a dict", {"type": "text", "text": "kept"}],
        )
        self.assertEqual(msg.get_text(), "kept")

    def test_text_part_with_missing_text_field_yields_empty(self):
        msg = ChatMessage(
            role="user",
            content=[{"type": "text"}],
        )
        self.assertEqual(msg.get_text(), "")


class TestChatCompletionRequestAcceptsStructuredContent(unittest.TestCase):
    """End-to-end: a request body with structured content must validate."""

    def test_request_with_string_content_validates(self):
        req = ChatCompletionRequest(
            model="meta-model",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
        )
        self.assertEqual(len(req.messages), 2)

    def test_request_with_list_content_validates(self):
        req = ChatCompletionRequest(
            model="meta-model",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Summarise this"},
                        {"type": "image_url", "url": "https://example.com/x.png"},
                    ],
                },
            ],
        )
        self.assertIsInstance(req.messages[0].content, list)

    def test_get_user_prompt_works_with_list_content(self):
        req = ChatCompletionRequest(
            model="meta-model",
            messages=[
                {"role": "system", "content": "sys"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {"type": "image_url", "url": "https://example.com/x.png"},
                        {"type": "text", "text": "this image"},
                    ],
                },
            ],
        )
        self.assertEqual(req.get_user_prompt(), "describe this image")

    def test_get_system_prompt_works_with_list_content(self):
        req = ChatCompletionRequest(
            model="meta-model",
            messages=[
                {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": "You are"},
                        {"type": "text", "text": "concise."},
                    ],
                },
                {"role": "user", "content": "hi"},
            ],
        )
        self.assertEqual(req.get_system_prompt(), "You are concise.")

    def test_get_user_prompt_returns_last_user_with_list_content(self):
        req = ChatCompletionRequest(
            model="meta-model",
            messages=[
                {"role": "user", "content": [{"type": "text", "text": "first"}]},
                {"role": "user", "content": [{"type": "text", "text": "second"}]},
                {"role": "user", "content": [{"type": "text", "text": "third"}]},
            ],
        )
        self.assertEqual(req.get_user_prompt(), "third")


class TestChatMessageValidation(unittest.TestCase):
    """Valid tool-loop messages are accepted; invalid roles/types are not."""

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValidationError):
            ChatMessage(role="function", content="x")

    def test_non_string_non_list_content_rejected(self):
        with self.assertRaises(ValidationError):
            ChatMessage(role="user", content=123)

    def test_tool_result_message_accepted(self):
        msg = ChatMessage(role="tool", content="file contents", tool_call_id="call_1")
        self.assertEqual(msg.tool_call_id, "call_1")

    def test_assistant_tool_call_without_content_accepted(self):
        msg = ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }],
        )
        self.assertEqual(msg.tool_calls[0].function.name, "read_file")
        self.assertEqual(msg.get_text(), "")


if __name__ == "__main__":
    unittest.main()
