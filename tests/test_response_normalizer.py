import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.response_normalizer import ResponseNormalizer


class TestResponseNormalizer(unittest.TestCase):

    def setUp(self):
        self.normalizer = ResponseNormalizer()

    def test_remove_preamble_ai(self):
        content = "As an AI assistant, I can help you with that."
        result = self.normalizer.normalize(content)
        self.assertFalse(result.startswith("As an AI"))
        self.assertFalse(result.startswith("As an AI assistant"))

    def test_remove_preamble_certainly(self):
        content = "Certainly! Here's the answer you requested."
        result = self.normalizer.normalize(content)
        self.assertFalse(result.startswith("Certainly"))
        self.assertFalse(result.startswith("Certainly!"))

    def test_remove_preamble_sure(self):
        content = "Sure thing! Let me help you."
        result = self.normalizer.normalize(content)
        self.assertFalse(result.startswith("Sure"))
        self.assertFalse(result.startswith("Sure thing"))

    def test_remove_preamble_let_me(self):
        content = "Let me explain this to you."
        result = self.normalizer.normalize(content)
        self.assertFalse(result.startswith("Let me"))
        self.assertFalse(result.startswith("I'll"))

    def test_remove_empty_code_blocks(self):
        content = "Here is the code:\n```python\n```\nDone."
        result = self.normalizer.normalize(content)
        self.assertNotIn("```python\n```", result)

    def test_standardize_whitespace(self):
        content = "Line 1\n\n\n\nLine 2\n\n\n\nLine 3"
        result = self.normalizer.normalize(content)
        lines = [l for l in result.split('\n') if l.strip()]
        self.assertEqual(len(lines), 3)

    def test_json_fix_unquoted_keys(self):
        content = '{name: "John", age: 30}'
        result = self.normalizer.normalize(content, {"type": "json_object"})
        import json
        try:
            json.loads(result)
            self.assertTrue(True)
        except json.JSONDecodeError:
            self.fail("Failed to parse JSON with unquoted keys")

    def test_json_fix_single_quotes(self):
        content = "{'name': 'John', 'age': 30}"
        result = self.normalizer.normalize(content, {"type": "json_object"})
        import json
        try:
            json.loads(result)
            self.assertTrue(True)
        except json.JSONDecodeError:
            self.fail("Failed to parse JSON with single quotes")

    def test_json_fix_trailing_commas(self):
        content = '{"name": "John", "age": 30,}'
        result = self.normalizer.normalize(content, {"type": "json_object"})
        import json
        try:
            json.loads(result)
            self.assertTrue(True)
        except json.JSONDecodeError:
            self.fail("Failed to parse JSON with trailing comma")

    def test_json_extract_from_markdown(self):
        content = 'Here is the JSON:\n```json\n{"name": "John"}\n```'
        result = self.normalizer.normalize(content, {"type": "json_object"})
        import json
        try:
            parsed = json.loads(result)
            self.assertEqual(parsed.get("name"), "John")
        except json.JSONDecodeError:
            self.fail("Failed to extract JSON from markdown")

    def test_json_no_changes_when_valid(self):
        content = '{"name": "John", "age": 30}'
        result = self.normalizer.normalize(content, {"type": "json_object"})
        import json
        parsed = json.loads(result)
        self.assertEqual(parsed["name"], "John")
        self.assertEqual(parsed["age"], 30)

    def test_preserve_normal_text(self):
        content = "This is a normal response without any issues."
        result = self.normalizer.normalize(content)
        self.assertIn("normal response", result)

    def test_looks_like_json(self):
        self.assertTrue(self.normalizer._looks_like_json('{"key": "value"}'))
        self.assertTrue(self.normalizer._looks_like_json('[1, 2, 3]'))
        self.assertFalse(self.normalizer._looks_like_json("Just text"))
        self.assertFalse(self.normalizer._looks_like_json("# Header"))


if __name__ == '__main__':
    unittest.main()
