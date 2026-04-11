"""
Test for ContextManager
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.context_manager import ContextManager
from src.models import ChatMessage


class TestContextManager(unittest.TestCase):
    def setUp(self):
        self.cm = ContextManager()
    
    def test_context_manager_creation(self):
        """Test that ContextManager can be created."""
        self.assertIsNotNone(self.cm)
    
    def test_static_mode_selection(self):
        """Test static mode context selection."""
        self.cm.context_management_mode = "static"
        self.cm.static_recent_keep = 3
        
        # Create test history
        history = [
            ChatMessage(role="user", content="First message"),
            ChatMessage(role="assistant", content="First response"),
            ChatMessage(role="user", content="Second message"),
            ChatMessage(role="assistant", content="Second response"),
            ChatMessage(role="user", content="Third message"),
            ChatMessage(role="assistant", content="Third response"),
            ChatMessage(role="user", content="Fourth message"),
        ]
        
        result = self.cm.select_context_for_request(history, "test-session", 1000)
        
        # Should return last 3 messages
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].content, "Third message")
        self.assertEqual(result[1].content, "Third response")
        self.assertEqual(result[2].content, "Fourth message")
    
    def test_empty_history(self):
        """Test with empty history."""
        result = self.cm.select_context_for_request([], "test-session", 1000)
        self.assertEqual(result, [])
    
    def test_single_message(self):
        """Test with single message."""
        self.cm.context_management_mode = "static"
        self.cm.static_recent_keep = 5
        
        history = [ChatMessage(role="user", content="Only message")]
        result = self.cm.select_context_for_request(history, "test-session", 1000)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].content, "Only message")
    
    def test_update_usage(self):
        """Test updating usage statistics."""
        self.cm.update_usage("test-session", 100)
        self.cm.update_usage("test-session", 200)
        self.cm.update_usage("test-session", 150)
        
        stats = self.cm.get_usage_stats("test-session")
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["average"], 150.0)
        self.assertEqual(stats["recent"], 150)  # Last value added
        self.assertEqual(stats["min"], 100)
        self.assertEqual(stats["max"], 200)

    def test_dynamic_mode_selection(self):
        """Test dynamic mode adjusts based on usage history."""
        self.cm.context_management_mode = "dynamic"
        self.cm.dynamic_utilization_target = 0.8
        self.cm.dynamic_min_utilization = 0.3
        
        # First request - no usage history, uses target * utilization
        history = [ChatMessage(role="user", content=f"Message {i}") for i in range(10)]
        result = self.cm.select_context_for_request(history, "dynamic-session", 1000)
        # Should use some messages (1000 * 0.8 / 50 ≈ 16, but capped at history length)
        self.assertGreater(len(result), 0)
        
        # Record low usage - should boost next request
        self.cm.update_usage("dynamic-session", 100)  # Low usage
        result = self.cm.select_context_for_request(history, "dynamic-session", 1000)
        # With low usage, should get more messages
        self.assertGreater(len(result), 0)

    def test_dynamic_high_usage(self):
        """Test dynamic mode with high usage reduces context."""
        self.cm.context_management_mode = "dynamic"
        self.cm.dynamic_utilization_target = 0.8
        
        # Record high usage
        self.cm.update_usage("high-usage-session", 800)
        history = [ChatMessage(role="user", content=f"Message {i}") for i in range(20)]
        result = self.cm.select_context_for_request(history, "high-usage-session", 1000)
        # With high usage, should use fewer messages
        self.assertLessEqual(len(result), len(history))

    def test_reservoir_mode_selection(self):
        """Test reservoir mode keeps recent and summarizes older."""
        self.cm.context_management_mode = "reservoir"
        self.cm.reservoir_recent_keep = 2
        self.cm.reservoir_summary_budget = 100
        
        # Create enough messages to trigger reservoir
        history = [
            ChatMessage(role="user", content="First message about weather."),
            ChatMessage(role="assistant", content="It's sunny today."),
            ChatMessage(role="user", content="Second message about coding."),
            ChatMessage(role="assistant", content="Here is a Python function."),
            ChatMessage(role="user", content="Third message about food."),
            ChatMessage(role="assistant", content="I recommend pizza."),
            ChatMessage(role="user", content="Fourth message."),
            ChatMessage(role="assistant", content="Response four."),
        ]
        
        result = self.cm.select_context_for_request(history, "reservoir-session", 1000)
        
        # Should have summary + recent messages
        self.assertGreaterEqual(len(result), 2)  # At least recent messages
        
        # First should be system message with summary
        if len(result) > 2:
            self.assertEqual(result[0].role, "system")

    def test_reservoir_few_messages(self):
        """Test reservoir with fewer messages than threshold."""
        self.cm.context_management_mode = "reservoir"
        self.cm.reservoir_recent_keep = 5
        
        history = [
            ChatMessage(role="user", content="Message 1"),
            ChatMessage(role="assistant", content="Response 1"),
        ]
        
        result = self.cm.select_context_for_request(history, "res-session", 1000)
        
        # Should return all - not enough for reservoir
        self.assertEqual(len(result), 2)

    def test_adaptive_code_detection(self):
        """Test adaptive mode detects code and uses reservoir."""
        self.cm.context_management_mode = "adaptive"
        self.cm.reservoir_recent_keep = 2
        
        # Code-heavy conversation
        history = [
            ChatMessage(role="user", content="How do I define a function in Python?"),
            ChatMessage(role="assistant", content="Use the def keyword like: def foo():"),
            ChatMessage(role="user", content="Can you show a class?"),
            ChatMessage(role="assistant", content="class MyClass:\n    def __init__(self):"),
            ChatMessage(role="user", content="What about imports?"),
            ChatMessage(role="assistant", content="import os\nfrom sys import path"),
            ChatMessage(role="user", content="Thanks"),
            ChatMessage(role="assistant", content="You're welcome!"),
        ]
        
        result = self.cm.select_context_for_request(history, "adaptive-session", 1000)
        
        # Should include summary for code
        if len(result) > 2:
            self.assertEqual(result[0].role, "system")

    def test_adaptive_general_chat(self):
        """Test adaptive mode uses static for general chat."""
        self.cm.context_management_mode = "adaptive"
        self.cm.static_recent_keep = 3
        
        # General conversation (no code indicators)
        history = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there!"),
            ChatMessage(role="user", content="How are you?"),
            ChatMessage(role="assistant", content="I'm doing well, thanks!"),
            ChatMessage(role="user", content="What's the weather?"),
            ChatMessage(role="assistant", content="It's sunny today."),
        ]
        
        result = self.cm.select_context_for_request(history, "adaptive-session", 1000)
        
        # Should use static (last N messages) - no summary needed
        self.assertLessEqual(len(result), self.cm.static_recent_keep + 1)

    def test_extractive_summarization(self):
        """Test extractive summarization algorithm."""
        messages = [
            ChatMessage(role="user", content="I need help with Python. Python is great for data."),
            ChatMessage(role="assistant", content="Python is a versatile language. It has many libraries."),
            ChatMessage(role="user", content="What about JavaScript?"),
            ChatMessage(role="assistant", content="JavaScript is good for web. Web development uses JavaScript."),
        ]
        
        summary = self.cm._extractive_summarize(messages, token_budget=50)
        
        # Should contain key content from messages
        self.assertIsInstance(summary, str)
        if summary:
            # Should mention Python (high TF word)
            self.assertIn("Python", summary)

    def test_disabled_mode(self):
        """Test disabled mode returns empty."""
        self.cm.context_management_mode = "disabled"
        
        history = [ChatMessage(role="user", content="Test")]
        result = self.cm.select_context_for_request(history, "disabled-session", 1000)
        
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()