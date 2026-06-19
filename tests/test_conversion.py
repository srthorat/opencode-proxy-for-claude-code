"""Tests for conversion/request.py (_anthropic_to_openai) and
conversion/response.py (_openai_to_anthropic)."""
import json
import pytest

from conversion.request import _anthropic_to_openai
from conversion.response import _openai_to_anthropic


# ---------------------------------------------------------------------------
# _anthropic_to_openai
# ---------------------------------------------------------------------------

class TestAnthropicToOpenAI:
    def test_basic_string_message(self):
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        result = _anthropic_to_openai(payload)
        assert result["messages"] == [{"role": "user", "content": "Hello"}]

    def test_string_system_becomes_system_message(self):
        payload = {
            "model": "test-model",
            "system": "You are helpful",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        result = _anthropic_to_openai(payload)
        assert result["messages"][0] == {"role": "system", "content": "You are helpful"}
        assert result["messages"][1] == {"role": "user", "content": "Hi"}

    def test_list_system_becomes_system_message(self):
        payload = {
            "model": "test-model",
            "system": [{"type": "text", "text": "Be concise"}],
            "messages": [{"role": "user", "content": "Hi"}],
        }
        result = _anthropic_to_openai(payload)
        assert result["messages"][0]["role"] == "system"
        assert "Be concise" in result["messages"][0]["content"]

    def test_tool_use_blocks_to_assistant_tool_calls(self):
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me search"},
                        {
                            "type": "tool_use",
                            "id": "toolu_001",
                            "name": "search",
                            "input": {"query": "python"},
                        },
                    ],
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        msg = result["messages"][0]
        assert msg["role"] == "assistant"
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["id"] == "toolu_001"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "search"
        assert json.loads(tc["function"]["arguments"]) == {"query": "python"}

    def test_tool_use_text_preserved_in_content(self):
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Calling tool now"},
                        {"type": "tool_use", "id": "t1", "name": "fn", "input": {}},
                    ],
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        assert result["messages"][0]["content"] == "Calling tool now"

    def test_tool_result_blocks_to_tool_messages(self):
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_001",
                            "content": "search result",
                        }
                    ],
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        msg = result["messages"][0]
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "toolu_001"
        assert msg["content"] == "search result"

    def test_tool_result_with_list_content(self):
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "t1",
                            "content": [{"type": "text", "text": "found it"}],
                        }
                    ],
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        assert "found it" in result["messages"][0]["content"]

    def test_tool_result_accompanying_text_emitted_as_user_message(self):
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "res"},
                        {"type": "text", "text": "Now summarise"},
                    ],
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        # One tool message + one user message
        assert result["messages"][0]["role"] == "tool"
        assert result["messages"][1] == {"role": "user", "content": "Now summarise"}

    def test_image_base64_converted(self):
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in the image?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "abc123",
                            },
                        },
                    ],
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        msg = result["messages"][0]
        assert isinstance(msg["content"], list)
        assert msg["content"][0] == {"type": "text", "text": "What's in the image?"}
        image_part = msg["content"][1]
        assert image_part["type"] == "image_url"
        assert "data:image/png;base64,abc123" in image_part["image_url"]["url"]

    def test_image_url_converted(self):
        payload = {
            "model": "test-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": "https://example.com/img.png"},
                        }
                    ],
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        image_part = result["messages"][0]["content"][0]
        assert image_part["image_url"]["url"] == "https://example.com/img.png"

    def test_single_text_block_becomes_plain_string(self):
        payload = {
            "model": "test-model",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hello"}]}
            ],
        }
        result = _anthropic_to_openai(payload)
        assert result["messages"][0]["content"] == "hello"

    def test_empty_content_list_produces_empty_string(self):
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": []}],
        }
        result = _anthropic_to_openai(payload)
        assert result["messages"][0]["content"] == ""

    def test_tools_converted_to_openai_functions(self):
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "name": "search",
                    "description": "Search the web",
                    "input_schema": {
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                        "required": ["q"],
                    },
                }
            ],
        }
        result = _anthropic_to_openai(payload)
        assert len(result["tools"]) == 1
        tool = result["tools"][0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "search"
        assert tool["function"]["description"] == "Search the web"
        assert tool["function"]["parameters"]["type"] == "object"

    def test_tool_choice_auto(self):
        payload = {
            "model": "m",
            "messages": [],
            "tool_choice": {"type": "auto"},
        }
        assert _anthropic_to_openai(payload)["tool_choice"] == "auto"

    def test_tool_choice_any_becomes_required(self):
        payload = {"model": "m", "messages": [], "tool_choice": {"type": "any"}}
        assert _anthropic_to_openai(payload)["tool_choice"] == "required"

    def test_tool_choice_disabled_becomes_none(self):
        payload = {"model": "m", "messages": [], "tool_choice": {"type": "disabled"}}
        assert _anthropic_to_openai(payload)["tool_choice"] == "none"

    def test_tool_choice_specific_tool(self):
        payload = {
            "model": "m",
            "messages": [],
            "tool_choice": {"type": "tool", "name": "my_fn"},
        }
        assert _anthropic_to_openai(payload)["tool_choice"] == {
            "type": "function",
            "function": {"name": "my_fn"},
        }

    def test_scalar_params_forwarded(self):
        payload = {
            "model": "m",
            "messages": [],
            "max_tokens": 100,
            "temperature": 0.7,
            "stream": True,
        }
        result = _anthropic_to_openai(payload)
        assert result["max_tokens"] == 100
        assert result["temperature"] == 0.7
        assert result["stream"] is True


# ---------------------------------------------------------------------------
# _openai_to_anthropic
# ---------------------------------------------------------------------------

class TestOpenAIToAnthropic:
    def test_basic_text_response(self):
        oai_resp = {
            "id": "chatcmpl-123",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        result = _openai_to_anthropic(oai_resp, "test-model")
        assert result["type"] == "message"
        assert result["role"] == "assistant"
        assert result["model"] == "test-model"
        assert result["content"] == [{"type": "text", "text": "Hello!"}]
        assert result["stop_reason"] == "end_turn"
        assert result["usage"]["input_tokens"] == 10
        assert result["usage"]["output_tokens"] == 5

    def test_tool_call_response(self):
        oai_resp = {
            "id": "chatcmpl-456",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "search",
                                    "arguments": '{"query": "test"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }
        result = _openai_to_anthropic(oai_resp, "test-model")
        assert result["stop_reason"] == "tool_use"
        assert len(result["content"]) == 1
        block = result["content"][0]
        assert block["type"] == "tool_use"
        assert block["id"] == "call_abc"
        assert block["name"] == "search"
        assert block["input"] == {"query": "test"}

    def test_text_and_tool_calls_combined(self):
        oai_resp = {
            "id": "x",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Let me search",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "fn", "arguments": "{}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {},
        }
        result = _openai_to_anthropic(oai_resp, "m")
        assert result["content"][0] == {"type": "text", "text": "Let me search"}
        assert result["content"][1]["type"] == "tool_use"

    def test_finish_reason_length_maps_to_max_tokens(self):
        oai_resp = {
            "id": "x",
            "choices": [
                {
                    "message": {"content": "...", "tool_calls": None},
                    "finish_reason": "length",
                }
            ],
            "usage": {},
        }
        result = _openai_to_anthropic(oai_resp, "m")
        assert result["stop_reason"] == "max_tokens"

    def test_unknown_finish_reason_defaults_to_end_turn(self):
        oai_resp = {
            "id": "x",
            "choices": [
                {
                    "message": {"content": "ok", "tool_calls": None},
                    "finish_reason": "content_filter",
                }
            ],
            "usage": {},
        }
        result = _openai_to_anthropic(oai_resp, "m")
        assert result["stop_reason"] == "end_turn"

    def test_id_preserved(self):
        oai_resp = {
            "id": "chatcmpl-myid",
            "choices": [
                {
                    "message": {"content": "ok", "tool_calls": None},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }
        result = _openai_to_anthropic(oai_resp, "m")
        assert result["id"] == "chatcmpl-myid"

    def test_missing_id_generates_fallback(self):
        oai_resp = {
            "choices": [
                {
                    "message": {"content": "ok", "tool_calls": None},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }
        result = _openai_to_anthropic(oai_resp, "m")
        assert result["id"].startswith("msg_")

    def test_malformed_tool_arguments_dont_crash(self):
        oai_resp = {
            "id": "x",
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "fn", "arguments": "not-json"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {},
        }
        # Should not raise
        result = _openai_to_anthropic(oai_resp, "m")
        assert result["content"][0]["input"] == {}
