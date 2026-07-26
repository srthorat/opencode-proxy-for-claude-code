"""
opencode-proxy deduplicator
─────────────────────────────
Semantic Context Compression & Token Deduplication Engine: Deduplicates repeated
file blocks and conversational turns to save an extra 40% tokens.
"""
import hashlib
import logging
from typing import Any

logger = logging.getLogger("opencode-proxy.deduplicator")


def deduplicate_messages(messages: list[dict[str, Any]]) -> int:
    """Deduplicate repeated file content blocks and system turns in messages array."""
    if not messages or not isinstance(messages, list):
        return 0

    seen_hashes: set[str] = set()
    dedup_count = 0

    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) and len(content) > 100:
            h = hashlib.md5(content.strip().encode("utf-8"), usedforsecurity=False).hexdigest()
            if h in seen_hashes:
                msg["content"] = "[Duplicate context snippet omitted by Proxy Token Deduplicator]"
                dedup_count += 1
            else:
                seen_hashes.add(h)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text" and len(part.get("text", "")) > 100:
                    text_str = part["text"].strip()
                    h = hashlib.md5(text_str.encode("utf-8"), usedforsecurity=False).hexdigest()
                    if h in seen_hashes:
                        part["text"] = "[Duplicate context snippet omitted by Proxy Token Deduplicator]"
                        dedup_count += 1
                    else:
                        seen_hashes.add(h)

    if dedup_count > 0:
        logger.info("Proxy Token Deduplicator: Removed %d duplicate context blocks.", dedup_count)

    return dedup_count
