import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from conversion.google import (
    _anthropic_to_google,
    _google_to_anthropic,
    _google_stream_to_anthropic,
)


def test_anthropic_to_google_basic_text():
    payload = {
        "model": "gemma-4-31b-it",
        "messages": [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        "temperature": 0.5,
    }
    result = _anthropic_to_google(payload)
    
    assert "contents" in result
    assert len(result["contents"]) == 2
    assert result["contents"][0]["role"] == "user"
    assert result["contents"][0]["parts"][0]["text"] == "Hello!"
    assert result["contents"][1]["role"] == "model"
    assert result["contents"][1]["parts"][0]["text"] == "Hi there!"
    
    assert "generationConfig" in result
    assert result["generationConfig"]["temperature"] == 0.5


def test_anthropic_to_google_with_system_instruction():
    payload = {
        "model": "gemma-4-31b-it",
        "system": "You are a helpful assistant.",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    result = _anthropic_to_google(payload)
    
    assert "systemInstruction" in result
    assert result["systemInstruction"]["parts"][0]["text"] == "You are a helpful assistant."


def test_anthropic_to_google_with_image():
    payload = {
        "model": "gemma-4-31b-it",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image:"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "abc123base64",
                        },
                    },
                ],
            }
        ],
    }
    result = _anthropic_to_google(payload)
    
    parts = result["contents"][0]["parts"]
    assert len(parts) == 2
    assert parts[0]["text"] == "Describe this image:"
    assert parts[1]["inlineData"]["mimeType"] == "image/png"
    assert parts[1]["inlineData"]["data"] == "abc123base64"


def test_anthropic_to_google_with_tools_and_tool_choice():
    payload = {
        "model": "gemma-4-31b-it",
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "tools": [
            {
                "name": "calculator",
                "description": "Perform basic arithmetic.",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            }
        ],
        "tool_choice": {"type": "tool", "name": "calculator"},
    }
    result = _anthropic_to_google(payload)
    
    assert "tools" in result
    fd = result["tools"][0]["functionDeclarations"][0]
    assert fd["name"] == "calculator"
    assert fd["description"] == "Perform basic arithmetic."
    
    assert "toolConfig" in result
    calling_config = result["toolConfig"]["functionCallingConfig"]
    assert calling_config["mode"] == "ANY"
    assert calling_config["allowedFunctionNames"] == ["calculator"]


def test_anthropic_to_google_with_tool_result():
    payload = {
        "model": "gemma-4-31b-it",
        "messages": [
            {
                "role": "user",
                "content": "Call calculator",
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_calculator_1",
                        "name": "calculator",
                        "input": {"expression": "2+2"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_calculator_1",
                        "content": "4",
                    }
                ],
            },
        ],
    }
    result = _anthropic_to_google(payload)
    
    contents = result["contents"]
    assert len(contents) == 3
    
    # Assistant tool use call
    assert "functionCall" in contents[1]["parts"][0]
    assert contents[1]["parts"][0]["functionCall"]["name"] == "calculator"
    
    # User tool result response
    assert "functionResponse" in contents[2]["parts"][0]
    fn_resp = contents[2]["parts"][0]["functionResponse"]
    assert fn_resp["name"] == "calculator"
    assert fn_resp["response"] == {"result": "4"}


def test_anthropic_to_google_with_thinking():
    payload = {
        "model": "gemma-4-31b-it",
        "messages": [{"role": "user", "content": "Write a sorting algorithm"}],
        "thinking": {"type": "enabled", "budget_tokens": 2048},
    }
    result = _anthropic_to_google(payload)
    
    assert "generationConfig" in result
    assert "thinkingConfig" in result["generationConfig"]
    assert result["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 2048


def test_google_to_anthropic_basic_response():
    google_response = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "The answer is 4."}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 5,
        },
    }
    
    result = _google_to_anthropic(google_response, "gemma-4-31b-it")
    
    assert result["role"] == "assistant"
    assert result["model"] == "gemma-4-31b-it"
    assert result["content"][0]["text"] == "The answer is 4."
    assert result["stop_reason"] == "end_turn"
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5


class MockResponse:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_google_stream_to_anthropic():
    chunks = [
        b'data: {"candidates": [{"content": {"parts": [{"text": "Hello"}], "role": "model"}}]}\n',
        b'data: {"candidates": [{"content": {"parts": [{"text": " world!"}], "role": "model"}}], "usageMetadata": {"candidatesTokenCount": 3}, "finishReason": "STOP"}\n',
    ]
    mock_resp = MockResponse(chunks)
    
    events = []
    async for event in _google_stream_to_anthropic(mock_resp, "gemma-4-31b-it"):
        events.append(event)
        
    # Standard yields: message_start, ping, content_block_start, content_block_delta (Hello),
    # content_block_delta ( world!), content_block_stop, message_delta, message_stop
    assert len(events) >= 8
    
    assert b"message_start" in events[0]
    assert b"ping" in events[1]
    assert b"content_block_start" in events[2]
    
    # Delta content check
    hello_delta = json.loads(events[3].decode().split("data: ")[1])
    assert hello_delta["delta"]["text"] == "Hello"
    
    world_delta = json.loads(events[4].decode().split("data: ")[1])
    assert world_delta["delta"]["text"] == " world!"
    
    assert b"content_block_stop" in events[5]
    
    message_delta = json.loads(events[6].decode().split("data: ")[1])
    assert message_delta["usage"]["output_tokens"] == 3
    assert message_delta["delta"]["stop_reason"] == "end_turn"
    
    assert b"message_stop" in events[7]
