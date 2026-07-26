"""
opencode-proxy progressive_aging
───────────────────────────────────
Engine 9: Progressive Aging & Summarization Engine.
Summarizes older turns (> 8 turns) into 2-sentence key summaries,
preserving full fidelity on recent active turns.
"""
import logging
from typing import Any

logger = logging.getLogger("opencode-proxy.progressive_aging")


def summarize_turn_content(content: Any) -> str:
    """Extract short 1-2 sentence representation of historical turn content."""
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
        text = " ".join(parts).strip()
    else:
        text = str(content)

    if len(text) > 150:
        return text[:140] + "..."
    return text


def age_and_summarize_turns(messages: list[dict[str, Any]], threshold_turns: int = 8) -> list[dict[str, Any]]:
    """Progressively summarize older turns when messages exceed threshold_turns."""
    if not isinstance(messages, list) or len(messages) <= threshold_turns:
        return messages

    recent_count = 4  # Keep last 4 turns completely intact
    older_messages = messages[:-recent_count]
    recent_messages = messages[-recent_count:]

    aged_summary_blocks = []
    for idx, msg in enumerate(older_messages):
        role = msg.get("role", "user")
        summary_text = summarize_turn_content(msg.get("content"))
        aged_summary_blocks.append(f"Turn {idx+1} ({role}): {summary_text}")

    compact_history_text = "[PROGRESSIVE_AGED_HISTORY_SUMMARY]\n" + "\n".join(aged_summary_blocks)

    aged_message = {
        "role": "user",
        "content": compact_history_text,
    }

    logger.info("Progressive Aging compressed %d older turns into summary block.", len(older_messages))
    return [aged_message] + recent_messages
