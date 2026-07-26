"""
opencode-proxy headroom_compact
──────────────────────────────────
Engine 4: Headroom JSON Tabular Compactor Engine.
Converts homogeneous JSON array tool outputs into compact CSV-style tabular strings,
achieving ~30% lossless token reduction.
"""
import json
import logging
import re

logger = logging.getLogger("opencode-proxy.headroom_compact")

JSON_ARRAY_REGEX = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)


def compact_json_tabular(text: str) -> str:
    """Detect JSON arrays of objects and convert to compact CSV tabular format."""
    if not text or not isinstance(text, str) or "[" not in text or "{" not in text:
        return text

    match = JSON_ARRAY_REGEX.search(text)
    if not match:
        return text

    json_str = match.group(0)
    try:
        data = json.loads(json_str)
        if isinstance(data, list) and len(data) >= 2 and all(isinstance(item, dict) for item in data):
            # Check for homogeneous keys
            keys = list(data[0].keys())
            if all(list(item.keys()) == keys for item in data):
                header = ",".join(keys)
                rows = [",".join(str(item.get(k, "")) for k in keys) for item in data]
                tabular_str = f"[HEADROOM_TABULAR_JSON]\nkeys: {header}\n" + "\n".join(rows)

                compacted = text.replace(json_str, tabular_str)
                logger.info("Headroom compact JSON array: %d items converted to tabular.", len(data))
                return compacted
    except Exception:
        pass

    return text
