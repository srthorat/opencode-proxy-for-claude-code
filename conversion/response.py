import json
import logging
import uuid

from conversion import STOP_REASON_MAP

logger = logging.getLogger("opencode-proxy")


def _openai_to_anthropic(resp: dict, model: str) -> dict:
    """Convert an OpenAI chat completion response body to Anthropic Messages format."""
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    content_str = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []

    content_blocks = []
    if content_str:
        content_blocks.append({"type": "text", "text": content_str})
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            input_data = json.loads(fn.get("arguments", "{}"))
        except Exception as e:
            logger.warning("Failed to parse tool call arguments as JSON: %s", e)
            input_data = {}
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": input_data,
        })

    finish_reason = choice.get("finish_reason", "stop")
    stop_reason = STOP_REASON_MAP.get(finish_reason, "end_turn")

    usage = resp.get("usage", {})
    return {
        "id": resp.get("id", f"msg_{uuid.uuid4().hex[:24]}"),
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }
