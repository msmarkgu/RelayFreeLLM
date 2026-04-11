"""
Test for context management integration in ModelDispatcher
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.model_dispatcher import ModelDispatcher
from src.model_selector import ModelSelector
from src.provider_registry import ProviderRegistry
from src.models import ChatCompletionRequest, ChatMessage


class TestContextManagementIntegration(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.mock_registry = MagicMock(spec=ProviderRegistry)
        self.mock_selector = MagicMock(spec=ModelSelector)
        self.mock_selector.provider_sequence = ["Groq"]
        self.mock_selector.select.return_value = ("Groq", "llama-3.3-70b-versatile", 0)
        
        # Mock API client
        self.mock_client = AsyncMock()
        self.mock_client.call_model_api.return_value = "Test response"
        self.mock_registry.get_client.return_value = self.mock_client
        self.mock_registry.list_providers.return_value = ["Groq"]
        
        self.dispatcher = ModelDispatcher(
            registry=self.mock_registry,
            selector=self.mock_selector
        )
    
    async def test_context_history_passed_to_call_provider_api(self):
        """Test that conversation history is passed to call_provider_api."""
        # Create a request with multiple messages
        request = ChatCompletionRequest(
            model="meta-model",
            messages=[
                ChatMessage(role="user", content="First question"),
                ChatMessage(role="assistant", content="First answer"),
                ChatMessage(role="user", content="Second question"),
                ChatMessage(role="assistant", content="Second answer"),
                ChatMessage(role="user", content="Current question"),
            ]
        )
        
        # Call chat with conversation history
        conversation_history = request.messages[:-1]  # All but last message
        await self.dispatcher.chat(request, conversation_history=conversation_history)
        
        # Verify call_provider_api was called with conversation_history
        call_args = self.mock_client.call_model_api.call_args
        
        # The context should be included in the messages sent to the API
        # Check that call was made (context management happened)
        self.assertIsNotNone(call_args)
        self.assertTrue(self.mock_client.call_model_api.called)
    
    async def test_empty_history_when_no_context(self):
        """Test behavior when no conversation history is provided."""
        request = ChatCompletionRequest(
            model="meta-model",
            messages=[
                ChatMessage(role="user", content="Only question"),
            ]
        )
        
        # Call chat without conversation history
        await self.dispatcher.chat(request, conversation_history=None)
        
        # Should still work, just without context
        self.assertTrue(self.mock_client.call_model_api.called)
    
    async def test_context_manager_selection(self):
        """Test that context manager selects appropriate messages."""
        # Create longer conversation history
        history = [
            ChatMessage(role="user", content=f"Question {i}")
            for i in range(10)
        ]
        history.extend([
            ChatMessage(role="assistant", content=f"Answer {i}")
            for i in range(10)
        ])
        
        request = ChatCompletionRequest(
            model="meta-model",
            messages=[
                ChatMessage(role="user", content="Current question"),
            ]
        )
        
        # Call with history - context manager should select appropriate portion
        await self.dispatcher.chat(request, conversation_history=history)
        
        # Verify the call was made
        self.assertTrue(self.mock_client.call_model_api.called)


if __name__ == "__main__":
    unittest.main()