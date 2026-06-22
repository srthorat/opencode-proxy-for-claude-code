import logging

logger = logging.getLogger("opencode-proxy")

_UNSUPPORTED = {"redacted_thinking", "thinking"}


def _strip_thinking_count(blocks: list) -> tuple[list, int]:
    """Recursively strip thinking/redacted_thinking blocks; return (cleaned, count_stripped)."""
    out = []
    stripped = 0
    for b in blocks:
        if isinstance(b, dict) and b.get("type") in _UNSUPPORTED:
            stripped += 1
            continue
        if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("content"), list):
            inner, n = _strip_thinking_count(b["content"])
            stripped += n
            b = {**b, "content": inner}
        out.append(b)
    return out, stripped


def _strip_thinking(blocks: list) -> list:
    """Strip thinking/redacted_thinking blocks from a content list, logging if any are found."""
    cleaned, n = _strip_thinking_count(blocks)
    if n:
        logger.warning("Stripped %d thinking block(s) from content list", n)
    return cleaned


def strip_thinking_from_system(system) -> "str | list":
    """Strip redacted_thinking/thinking blocks from the top-level system field.

    If system is an array (Anthropic extended format), drop unsupported blocks.
    Returns the cleaned value (string or list).
    """
    if not isinstance(system, list):
        return system
    cleaned = [b for b in system if not (isinstance(b, dict) and b.get("type") in _UNSUPPORTED)]
    if len(cleaned) != len(system):
        logger.warning(
            "Stripped %d thinking block(s) from system field", len(system) - len(cleaned)
        )
    return cleaned


def _sanitize_messages(messages: list, payload: dict) -> list:
    """Three-pass conversation sanitizer.

    Pass 1: Hoist inline system-role messages out of the messages array into the
            top-level 'system' field (only user/assistant are valid roles in the
            messages array).
    Pass 2: Strip redacted_thinking/thinking blocks; replace thinking-only turns
            with a placeholder so the conversation remains valid.
    Pass 3: Convert tool_result blocks that have no matching prior tool_use into
            plain text, preventing 'tool call result does not follow tool call'
            errors on strict providers.  Also splits user messages that mix
            tool_result and non-tool_result blocks (MiniMax rejects them).
    """
    # ── Pass 1: extract inline system messages ──────────────────────────────
    pass0 = []
    extra_system_parts = []
    for msg in messages:
        if msg.get("role") == "system":
            c = msg.get("content", "")
            if isinstance(c, str):
                extra_system_parts.append(c)
            elif isinstance(c, list):
                extra_system_parts.extend(
                    b.get("text", "") for b in c
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            logger.debug("Hoisting inline system message to top-level system field")
        else:
            pass0.append(msg)

    if extra_system_parts:
        existing = payload.get("system", "")
        if isinstance(existing, str):
            combined = "\n\n".join(filter(None, [existing] + extra_system_parts))
        elif isinstance(existing, list):
            existing_text = "\n\n".join(
                b.get("text", "") for b in existing
                if isinstance(b, dict) and b.get("type") == "text"
            )
            combined = "\n\n".join(filter(None, [existing_text] + extra_system_parts))
        else:
            combined = "\n\n".join(extra_system_parts)
        payload["system"] = combined

    # ── Pass 2: strip unsupported blocks ────────────────────────────────────
    pass1 = []
    for msg in pass0:
        content = msg.get("content")
        if not isinstance(content, list):
            pass1.append(msg)
            continue
        filtered = _strip_thinking(content)
        if not filtered:
            logger.debug(
                "Replacing thinking-only message with placeholder (role=%s)",
                msg.get("role"),
            )
            filtered = [{"type": "text", "text": "..."}]
        pass1.append({**msg, "content": filtered})

    # ── Pass 3: fix orphaned tool_results ────────────────────────────────────
    seen_tool_ids: set = set()
    result = []
    for msg in pass1:
        role = msg.get("role", "user")
        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue
        if role == "assistant":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                    seen_tool_ids.add(block["id"])
            result.append(msg)
        elif role == "user":
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tid = block.get("tool_use_id", "")
                    if tid in seen_tool_ids:
                        new_content.append(block)
                        seen_tool_ids.discard(tid)
                    else:
                        rc = block.get("content", "")
                        if isinstance(rc, list):
                            rc = " ".join(
                                b.get("text", "") for b in rc
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                        logger.debug(
                            "Converting orphaned tool_result to text (tool_use_id=%s)", tid
                        )
                        new_content.append({"type": "text", "text": str(rc) or "[tool result]"})
                else:
                    new_content.append(block)

            # Split user messages that mix tool_result and non-tool_result blocks.
            # Strict providers (e.g. MiniMax) reject mixed messages.
            # Emit: first a tool_result-only message, then a text-only message.
            tool_result_blocks = [
                b for b in new_content
                if isinstance(b, dict) and b.get("type") == "tool_result"
            ]
            other_blocks = [
                b for b in new_content
                if not (isinstance(b, dict) and b.get("type") == "tool_result")
            ]
            if tool_result_blocks and other_blocks:
                logger.debug("Splitting mixed user message into tool_results + text parts")
                result.append({**msg, "content": tool_result_blocks})
                result.append({**msg, "content": other_blocks})
            else:
                result.append({**msg, "content": new_content})
        else:
            result.append(msg)
    return result
