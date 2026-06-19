"""Tests for sanitization.py — _sanitize_messages and _strip_thinking."""
import pytest

from sanitization import _sanitize_messages, _strip_thinking


# ---------------------------------------------------------------------------
# _strip_thinking
# ---------------------------------------------------------------------------

class TestStripThinking:
    def test_removes_thinking_block(self):
        blocks = [
            {"type": "thinking", "thinking": "internal thoughts"},
            {"type": "text", "text": "actual content"},
        ]
        result = _strip_thinking(blocks)
        assert len(result) == 1
        assert result[0]["type"] == "text"

    def test_removes_redacted_thinking_block(self):
        blocks = [
            {"type": "redacted_thinking", "data": "opaque"},
            {"type": "text", "text": "visible"},
        ]
        result = _strip_thinking(blocks)
        assert len(result) == 1
        assert result[0]["type"] == "text"

    def test_preserves_non_thinking_blocks(self):
        blocks = [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "id": "t1", "name": "fn", "input": {}},
        ]
        result = _strip_thinking(blocks)
        assert len(result) == 2

    def test_strips_nested_thinking_in_tool_result(self):
        blocks = [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_123",
                "content": [
                    {"type": "thinking", "thinking": "internal"},
                    {"type": "text", "text": "result"},
                ],
            }
        ]
        result = _strip_thinking(blocks)
        assert len(result) == 1
        assert len(result[0]["content"]) == 1
        assert result[0]["content"][0]["type"] == "text"

    def test_empty_input_returns_empty(self):
        assert _strip_thinking([]) == []


# ---------------------------------------------------------------------------
# _sanitize_messages — Pass 1: system message hoisting
# ---------------------------------------------------------------------------

class TestSystemMessageHoisting:
    def test_hoists_system_role_to_payload(self):
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
        ]
        payload = {}
        result = _sanitize_messages(messages, payload)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert payload["system"] == "Be helpful"

    def test_hoisting_merges_with_existing_string_system(self):
        messages = [
            {"role": "system", "content": "Extra instruction"},
            {"role": "user", "content": "Hi"},
        ]
        payload = {"system": "You are an AI"}
        _sanitize_messages(messages, payload)
        assert "You are an AI" in payload["system"]
        assert "Extra instruction" in payload["system"]

    def test_hoisting_merges_with_existing_list_system(self):
        messages = [
            {"role": "system", "content": "Appended"},
            {"role": "user", "content": "Hi"},
        ]
        payload = {"system": [{"type": "text", "text": "Base instruction"}]}
        _sanitize_messages(messages, payload)
        assert "Base instruction" in payload["system"]
        assert "Appended" in payload["system"]

    def test_system_message_with_list_content_hoisted(self):
        messages = [
            {"role": "system", "content": [{"type": "text", "text": "From list"}]},
            {"role": "user", "content": "Hello"},
        ]
        payload = {}
        _sanitize_messages(messages, payload)
        assert "From list" in payload["system"]

    def test_non_system_messages_pass_through(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        payload = {}
        result = _sanitize_messages(messages, payload)
        assert len(result) == 2
        assert "system" not in payload


# ---------------------------------------------------------------------------
# _sanitize_messages — Pass 2: thinking block stripping
# ---------------------------------------------------------------------------

class TestThinkingBlockStripping:
    def test_thinking_only_turn_gets_placeholder(self):
        messages = [
            {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "..."}],
            }
        ]
        result = _sanitize_messages(messages, {})
        assert result[0]["content"] == [{"type": "text", "text": "..."}]

    def test_mixed_turn_strips_only_thinking_blocks(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "private"},
                    {"type": "text", "text": "public"},
                ],
            }
        ]
        result = _sanitize_messages(messages, {})
        content = result[0]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "public"

    def test_string_content_passes_through_unchanged(self):
        messages = [{"role": "user", "content": "plain text"}]
        result = _sanitize_messages(messages, {})
        assert result[0]["content"] == "plain text"


# ---------------------------------------------------------------------------
# _sanitize_messages — Pass 3: orphaned tool_result conversion
# ---------------------------------------------------------------------------

class TestOrphanedToolResults:
    def test_orphaned_tool_result_becomes_text(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "ghost_id", "content": "result text"}
                ],
            }
        ]
        result = _sanitize_messages(messages, {})
        content = result[0]["content"]
        assert content[0]["type"] == "text"
        assert "result text" in content[0]["text"]

    def test_matched_tool_result_preserved(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_abc", "name": "my_tool", "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_abc", "content": "tool output"}
                ],
            },
        ]
        result = _sanitize_messages(messages, {})
        assert result[1]["content"][0]["type"] == "tool_result"

    def test_orphaned_tool_result_with_list_content(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "no_match",
                        "content": [{"type": "text", "text": "list result"}],
                    }
                ],
            }
        ]
        result = _sanitize_messages(messages, {})
        assert result[0]["content"][0]["type"] == "text"
        assert "list result" in result[0]["content"][0]["text"]

    def test_empty_orphaned_tool_result_gets_placeholder(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "no_match", "content": ""}
                ],
            }
        ]
        result = _sanitize_messages(messages, {})
        assert result[0]["content"][0]["text"] == "[tool result]"


# ---------------------------------------------------------------------------
# _sanitize_messages — Pass 3: mixed user message splitting
# ---------------------------------------------------------------------------

class TestMixedUserMessageSplitting:
    def test_splits_mixed_user_message(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_xyz", "name": "search", "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_xyz", "content": "found it"},
                    {"type": "text", "text": "Now what?"},
                ],
            },
        ]
        result = _sanitize_messages(messages, {})
        # assistant + tool_result part + text part = 3 messages
        assert len(result) == 3
        tool_msg = result[1]
        text_msg = result[2]
        assert tool_msg["content"][0]["type"] == "tool_result"
        assert text_msg["content"][0]["type"] == "text"
        assert text_msg["content"][0]["text"] == "Now what?"

    def test_pure_tool_result_message_not_split(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_a", "name": "fn", "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_a", "content": "res"}
                ],
            },
        ]
        result = _sanitize_messages(messages, {})
        # Should NOT be split — only 2 messages
        assert len(result) == 2

    def test_pure_text_user_message_not_split(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]}
        ]
        result = _sanitize_messages(messages, {})
        assert len(result) == 1
