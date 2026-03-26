import sys
import os
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from src.server import app

client = TestClient(app)

async def mock_streaming_generator():
    yield "Hello"
    yield " "
    yield "World"

@patch("src.router.get_dispatcher")
def test_chat_completions_streaming(mock_get_dispatcher):
    """Test that the /v1/chat/completions endpoint supports streaming with mocks."""
    mock_dispatcher = MagicMock()
    mock_dispatcher.chat = AsyncMock(return_value=mock_streaming_generator())
    mock_get_dispatcher.return_value = mock_dispatcher
    
    payload = {
        "model": "meta-model",
        "messages": [
            {"role": "user", "content": "Say hello world."}
        ],
        "stream": True
    }
    
    with client.stream("POST", "/v1/chat/completions", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        chunks = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                data_str = line[len("data: "):]
                if data_str == "[DONE]":
                    break
                data = json.loads(data_str)
                assert data["object"] == "chat.completion.chunk"
                content = data["choices"][0]["delta"].get("content", "")
                chunks.append(content)
        
        assert chunks == ["Hello", " ", "World"]
        print(f"\nStreamed response: {''.join(chunks)}")

if __name__ == "__main__":
    test_chat_completions_streaming()
