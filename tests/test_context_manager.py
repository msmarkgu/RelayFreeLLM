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


if __name__ == "__main__":
    unittest.main()