"""Contract checks for the recorded upstream stream fixtures."""

import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.stream_fixtures import load_stream


class TestStreamFixtures(unittest.TestCase):
    def test_text(self):
        chunks = load_stream("text")
        self.assertEqual(chunks[-1]["choices"][0]["finish_reason"], "stop")
        self.assertGreater(chunks[-1]["usage"]["total_tokens"], 0)

    def test_tool_use(self):
        chunks = load_stream("tool_use")
        first_call = chunks[0]["choices"][0]["delta"]["tool_calls"][0]
        self.assertEqual(first_call["function"]["name"], "read_file")
        args = "".join(
            chunk["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"]
            for chunk in chunks[:2]
        )
        self.assertEqual(args, '{"path":"notes/plan.md"}')
        self.assertEqual(chunks[-1]["choices"][0]["finish_reason"], "tool_calls")

    def test_parallel_tools(self):
        chunks = load_stream("parallel_tools")
        indices = {
            call["index"]
            for chunk in chunks
            for call in chunk["choices"][0]["delta"].get("tool_calls", [])
        }
        self.assertEqual(indices, {0, 1})

    def test_thinking(self):
        chunks = load_stream("thinking")
        reasoning = "".join(
            chunk["choices"][0]["delta"].get("reasoning_content", "")
            for chunk in chunks
        )
        self.assertIn("tool schema", reasoning)
        self.assertTrue(any("content" in c["choices"][0]["delta"] for c in chunks))

    def test_mid_stream_failure(self):
        chunks = load_stream("mid_stream_failure")
        self.assertIn("content", chunks[0]["choices"][0]["delta"])
        self.assertEqual(chunks[-1]["error"]["type"], "upstream_error")


if __name__ == "__main__":
    unittest.main()
