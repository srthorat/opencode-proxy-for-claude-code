"""Tests for conversion/streaming.py — _openai_stream_to_anthropic.

Feeds mock SSE byte sequences through the async generator and asserts the
emitted Anthropic SSE event sequence.  Covers:
  - Plain text streaming (text_delta events)
  - Tool call streaming (tool_use open/delta/close)
  - Mixed text + tool call
  - Empty stream (no content) → at least one block emitted
  - Parse error in mid-stream → message_stop still emitted
"""

import json
import pytest

from conversion.streaming import _openai_stream_to_anthropic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockResponse:
    """Minimal stub for an httpx streaming response."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


def sse(obj: dict) -> bytes:
    """Encode a dict as an SSE data line."""
    return f"data: {json.dumps(obj)}\n\n".encode()


def delta_chunk(
    content: str | None = None,
    tool_calls: list | None = None,
    finish_reason: str | None = None,
    usage: dict | None = None,
) -> bytes:
    """Build a minimal OpenAI SSE chunk."""
    d: dict = {}
    if content is not None:
        d["content"] = content
    if tool_calls is not None:
        d["tool_calls"] = tool_calls
    obj: dict = {"choices": [{"delta": d, "finish_reason": finish_reason}]}
    if usage is not None:
        obj["usage"] = usage
    return sse(obj)


async def collect_events(chunks: list[bytes]) -> list[dict]:
    """Drive the generator and collect all parsed SSE data payloads."""
    resp = MockResponse(chunks)
    events: list[dict] = []
    async for raw in _openai_stream_to_anthropic(resp, "test-model"):
        for line in raw.decode().split("\n"):
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return events


def event_types(events: list[dict]) -> list[str]:
    return [e.get("type", "") for e in events]


# ---------------------------------------------------------------------------
# Tests: plain text streaming
# ---------------------------------------------------------------------------

class TestPlainTextStreaming:
    @pytest.mark.asyncio
    async def test_emits_message_start(self):
        chunks = [
            delta_chunk(content="Hello"),
            delta_chunk(finish_reason="stop", usage={"completion_tokens": 5}),
            b"data: [DONE]\n\n",
        ]
        events = await collect_events(chunks)
        assert events[0]["type"] == "message_start"
        assert events[0]["message"]["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_emits_content_block_start_on_first_text(self):
        chunks = [
            delta_chunk(content="Hi"),
            delta_chunk(finish_reason="stop"),
        ]
        events = await collect_events(chunks)
        types = event_types(events)
        assert "content_block_start" in types

    @pytest.mark.asyncio
    async def test_text_delta_content_correct(self):
        chunks = [
            delta_chunk(content="Hello"),
            delta_chunk(content=" world"),
            delta_chunk(finish_reason="stop"),
        ]
        events = await collect_events(chunks)
        text_deltas = [
            e for e in events
            if e.get("type") == "content_block_delta"
            and e.get("delta", {}).get("type") == "text_delta"
        ]
        combined = "".join(e["delta"]["text"] for e in text_deltas)
        assert combined == "Hello world"

    @pytest.mark.asyncio
    async def test_emits_message_delta_with_stop_reason(self):
        chunks = [
            delta_chunk(content="ok"),
            delta_chunk(finish_reason="stop"),
        ]
        events = await collect_events(chunks)
        msg_delta = next(e for e in events if e.get("type") == "message_delta")
        assert msg_delta["delta"]["stop_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_usage_output_tokens_accumulated(self):
        """P0 #2: output_tokens must come from the final chunk's usage field."""
        chunks = [
            delta_chunk(content="ok"),
            delta_chunk(finish_reason="stop", usage={"completion_tokens": 42}),
        ]
        events = await collect_events(chunks)
        msg_delta = next(e for e in events if e.get("type") == "message_delta")
        assert msg_delta["usage"]["output_tokens"] == 42

    @pytest.mark.asyncio
    async def test_emits_message_stop(self):
        chunks = [
            delta_chunk(content="ok"),
            delta_chunk(finish_reason="stop"),
        ]
        events = await collect_events(chunks)
        assert events[-1]["type"] == "message_stop"

    @pytest.mark.asyncio
    async def test_length_finish_reason_maps_to_max_tokens(self):
        chunks = [delta_chunk(content="x"), delta_chunk(finish_reason="length")]
        events = await collect_events(chunks)
        msg_delta = next(e for e in events if e.get("type") == "message_delta")
        assert msg_delta["delta"]["stop_reason"] == "max_tokens"


# ---------------------------------------------------------------------------
# Tests: tool call streaming
# ---------------------------------------------------------------------------

class TestToolCallStreaming:
    @pytest.mark.asyncio
    async def test_emits_tool_use_content_block_start(self):
        chunks = [
            sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_abc", "function": {"name": "search", "arguments": ""}}
            ]}, "finish_reason": None}]}),
            sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": '{"q":"test"}'}}
            ]}, "finish_reason": None}]}),
            delta_chunk(finish_reason="tool_calls"),
        ]
        events = await collect_events(chunks)
        tool_start = next(
            (e for e in events
             if e.get("type") == "content_block_start"
             and e.get("content_block", {}).get("type") == "tool_use"),
            None,
        )
        assert tool_start is not None
        assert tool_start["content_block"]["name"] == "search"
        assert tool_start["content_block"]["id"] == "call_abc"

    @pytest.mark.asyncio
    async def test_tool_arguments_emitted_as_input_json_delta(self):
        chunks = [
            sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_x", "function": {"name": "fn", "arguments": ""}}
            ]}, "finish_reason": None}]}),
            sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": '{"a":1}'}}
            ]}, "finish_reason": None}]}),
            delta_chunk(finish_reason="tool_calls"),
        ]
        events = await collect_events(chunks)
        arg_delta = next(
            (e for e in events
             if e.get("type") == "content_block_delta"
             and e.get("delta", {}).get("type") == "input_json_delta"),
            None,
        )
        assert arg_delta is not None
        assert '{"a":1}' in arg_delta["delta"]["partial_json"]

    @pytest.mark.asyncio
    async def test_tool_calls_stop_reason_maps_to_tool_use(self):
        chunks = [
            sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "c", "function": {"name": "f", "arguments": ""}}
            ]}, "finish_reason": None}]}),
            delta_chunk(finish_reason="tool_calls"),
        ]
        events = await collect_events(chunks)
        msg_delta = next(e for e in events if e.get("type") == "message_delta")
        assert msg_delta["delta"]["stop_reason"] == "tool_use"

    @pytest.mark.asyncio
    async def test_content_block_stop_emitted_after_tool_use(self):
        chunks = [
            sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "c", "function": {"name": "f", "arguments": ""}}
            ]}, "finish_reason": None}]}),
            delta_chunk(finish_reason="tool_calls"),
        ]
        events = await collect_events(chunks)
        assert any(e.get("type") == "content_block_stop" for e in events)


# ---------------------------------------------------------------------------
# Tests: mixed text + tool call
# ---------------------------------------------------------------------------

class TestMixedTextAndToolCall:
    @pytest.mark.asyncio
    async def test_both_text_and_tool_blocks_emitted(self):
        chunks = [
            delta_chunk(content="Calling tool..."),
            sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "c1", "function": {"name": "search", "arguments": ""}}
            ]}, "finish_reason": None}]}),
            delta_chunk(finish_reason="tool_calls"),
        ]
        events = await collect_events(chunks)
        block_starts = [
            e for e in events if e.get("type") == "content_block_start"
        ]
        block_types = [e.get("content_block", {}).get("type") for e in block_starts]
        assert "text" in block_types
        assert "tool_use" in block_types


# ---------------------------------------------------------------------------
# Tests: empty stream
# ---------------------------------------------------------------------------

class TestEmptyStream:
    @pytest.mark.asyncio
    async def test_empty_stream_still_emits_message_stop(self):
        chunks = [b"data: [DONE]\n\n"]
        events = await collect_events(chunks)
        assert events[-1]["type"] == "message_stop"

    @pytest.mark.asyncio
    async def test_empty_stream_emits_at_least_one_content_block(self):
        """Anthropic clients require at least one content block."""
        chunks = [b"data: [DONE]\n\n"]
        events = await collect_events(chunks)
        assert any(e.get("type") == "content_block_start" for e in events)

    @pytest.mark.asyncio
    async def test_no_content_defaults_to_text_block(self):
        chunks = [b"data: [DONE]\n\n"]
        events = await collect_events(chunks)
        text_start = next(
            (e for e in events
             if e.get("type") == "content_block_start"
             and e.get("content_block", {}).get("type") == "text"),
            None,
        )
        assert text_start is not None


# ---------------------------------------------------------------------------
# Tests: error resilience (P0 #4)
# ---------------------------------------------------------------------------

class TestErrorResilience:
    @pytest.mark.asyncio
    async def test_parse_error_mid_stream_still_emits_message_stop(self):
        """A JSON parse error on a chunk must not prevent message_stop."""
        chunks = [
            b"data: not-valid-json\n\n",
            delta_chunk(content="after error"),
            delta_chunk(finish_reason="stop"),
        ]
        events = await collect_events(chunks)
        assert events[-1]["type"] == "message_stop"

    @pytest.mark.asyncio
    async def test_parse_error_content_after_error_still_received(self):
        chunks = [
            b"data: bad\n\n",
            delta_chunk(content="hello"),
            delta_chunk(finish_reason="stop"),
        ]
        events = await collect_events(chunks)
        text_deltas = [
            e for e in events
            if e.get("type") == "content_block_delta"
            and e.get("delta", {}).get("type") == "text_delta"
        ]
        assert any("hello" in e["delta"]["text"] for e in text_deltas)

    @pytest.mark.asyncio
    async def test_network_error_mid_stream_still_emits_message_stop(self):
        """If aiter_bytes raises, the generator must still emit message_stop."""

        class ErrorResponse:
            async def aiter_bytes(self):
                yield delta_chunk(content="start")
                raise ConnectionError("connection dropped")

        events: list[dict] = []
        async for raw in _openai_stream_to_anthropic(ErrorResponse(), "test-model"):
            for line in raw.decode().split("\n"):
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        assert events[-1]["type"] == "message_stop"
