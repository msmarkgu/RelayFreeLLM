"""Anthropic Messages adapter: request/response and SSE event contracts."""

import asyncio
import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.anthropic_adapter import (
    MessagesRequest,
    from_chat_response,
    stream_anthropic_events,
    to_chat_request,
)
from src.models import build_response
from tests.stream_fixtures import load_stream

USER_WITH_TOOL_LOOP = {
    "model": "claude-sonnet-5-5",
    "max_tokens": 1024,
    "system": "You are concise.",
    "messages": [
        {"role": "user", "content": "Read the plan."},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Checking."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_file",
                    "input": {"path": "notes/plan.md"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "Phase 1",
                }
            ],
        },
    ],
    "tools": [
        {
            "name": "read_file",
            "description": "Read a file",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        }
    ],
    "tool_choice": {"type": "any"},
}


async def internal_stream(name: str):
    """Replay an OpenAI-style fixture as internal dispatcher chunks."""
    for chunk in load_stream(name):
        if "error" in chunk:
            yield chunk
            continue
        delta = chunk["choices"][0]["delta"]
        if delta.get("content"):
            yield {"type": "content", "data": delta["content"]}
        if delta.get("tool_calls"):
            yield {"type": "content", "data": {"tool_calls": delta["tool_calls"]}}


def collect(name: str, request: MessagesRequest):
    return asyncio.run(
        _collect(stream_anthropic_events(internal_stream(name), request))
    )


async def _collect(gen):
    return [event async for event in gen]


class TestAnthropicRequestTranslation(unittest.TestCase):
    def test_tool_loop_translation(self):
        request = MessagesRequest(**USER_WITH_TOOL_LOOP)
        internal = to_chat_request(request)
        self.assertEqual(
            [m.role for m in internal.messages],
            ["system", "user", "assistant", "tool"],
        )
        assistant = internal.messages[2]
        self.assertEqual(assistant.tool_calls[0].function.name, "read_file")
        self.assertEqual(
            json.loads(assistant.tool_calls[0].function.arguments)["path"],
            "notes/plan.md",
        )
        self.assertEqual(internal.messages[3].tool_call_id, "toolu_1")
        self.assertEqual(internal.messages[3].content, "Phase 1")

    def test_tools_and_choice(self):
        internal = to_chat_request(MessagesRequest(**USER_WITH_TOOL_LOOP))
        self.assertEqual(internal.tools[0].function.name, "read_file")
        self.assertEqual(internal.tool_choice, "required")


class TestAnthropicResponseTranslation(unittest.TestCase):
    def test_text_and_tool_use(self):
        response = build_response(
            content="Reading now.",
            provider="Groq",
            model="qwen-3",
            latency_ms=1.0,
            attempt=1,
            prompt_tokens=9,
            completion_tokens=4,
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"x"}'},
            }],
        )
        message = from_chat_response(response, "claude-sonnet-5-5")
        self.assertTrue(message["id"].startswith("msg_"))
        self.assertEqual(message["stop_reason"], "tool_use")
        self.assertEqual(message["content"][0]["type"], "text")
        self.assertEqual(message["content"][1]["type"], "tool_use")
        self.assertEqual(message["content"][1]["input"], {"path": "x"})
        self.assertEqual(message["usage"]["input_tokens"], 9)
        self.assertEqual(message["usage"]["output_tokens"], 4)


class TestAnthropicStreamTranslation(unittest.TestCase):
    def setUp(self):
        self.request = MessagesRequest(
            model="claude-sonnet-5-5",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=128,
        )

    def test_text_stream(self):
        events = collect("text", self.request)
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "message_start")
        self.assertEqual(types[-1], "message_stop")
        text = "".join(
            e["delta"]["text"]
            for e in events
            if e["type"] == "content_block_delta"
            and e["delta"]["type"] == "text_delta"
        )
        self.assertEqual(text, "Hello world")
        delta = next(e for e in events if e["type"] == "message_delta")
        self.assertEqual(delta["delta"]["stop_reason"], "end_turn")
        self.assertGreater(delta["usage"]["output_tokens"], 0)

    def test_tool_use_stream(self):
        events = collect("tool_use", self.request)
        starts = [e for e in events if e["type"] == "content_block_start"]
        tool_start = starts[0]
        self.assertEqual(tool_start["content_block"]["type"], "tool_use")
        self.assertEqual(tool_start["index"], 0)
        self.assertEqual(tool_start["content_block"]["name"], "read_file")
        args = "".join(
            e["delta"]["partial_json"]
            for e in events
            if e.get("delta", {}).get("type") == "input_json_delta"
        )
        self.assertEqual(json.loads(args), {"path": "notes/plan.md"})
        delta = next(e for e in events if e["type"] == "message_delta")
        self.assertEqual(delta["delta"]["stop_reason"], "tool_use")

    def test_parallel_tools_stream(self):
        events = collect("parallel_tools", self.request)
        tools = [
            e["content_block"]
            for e in events
            if e["type"] == "content_block_start"
            and e["content_block"]["type"] == "tool_use"
        ]
        self.assertEqual({tool["name"] for tool in tools}, {"search", "read_file"})
        self.assertEqual(len({tool["id"] for tool in tools}), 2)

    def test_thinking_fixture_stream(self):
        events = collect("thinking", self.request)
        text = "".join(
            e["delta"]["text"]
            for e in events
            if e.get("delta", {}).get("type") == "text_delta"
        )
        self.assertIn("Done.", text)

    def test_mid_stream_failure(self):
        events = collect("mid_stream_failure", self.request)
        error = next(e for e in events if e["type"] == "error")
        self.assertEqual(error["error"]["type"], "upstream_error")


if __name__ == "__main__":
    unittest.main()
