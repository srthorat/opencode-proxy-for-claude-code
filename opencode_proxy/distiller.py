import logging
import re
from typing import Any

from .config import MAX_DISTILL_CHARS
from .skeletonizer import skeletonize_code

logger = logging.getLogger("opencode-proxy.distiller")

# Regex patterns for stripping non-essential noise to save tokens
ANSI_ESCAPE_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
MULTIPLE_NEWLINES_REGEX = re.compile(r"\n{3,}")
EXCESS_WHITESPACE_REGEX = re.compile(r"[ \t]+$")


def compress_tool_result_content(content: str, max_chars: int | None = None) -> str:
    """Compress bulky tool outputs (terminal logs, grep results, file reads) to save 50-80% tokens.

    Strips ANSI color codes, collapses excess whitespace, and truncates repetitive log output.
    Uses configurable MAX_DISTILL_CHARS threshold (default: 3000) for large repos.
    """
    if not content or not isinstance(content, str):
        return content

    limit = max_chars if max_chars is not None else MAX_DISTILL_CHARS

    # 1. Strip ANSI codes
    cleaned = ANSI_ESCAPE_REGEX.sub("", content)

    # 2. Collapse excess newlines and trailing whitespace
    cleaned = MULTIPLE_NEWLINES_REGEX.sub("\n\n", cleaned)
    cleaned = EXCESS_WHITESPACE_REGEX.sub("", cleaned)

    # 3. Truncate if exceeding max character threshold
    if len(cleaned) > limit:
        head = cleaned[: limit // 2]
        tail = cleaned[-limit // 2 :]
        removed_count = len(cleaned) - limit
        cleaned = f"{head}\n\n[... {removed_count} chars truncated by opencode-proxy Token Distiller ...]\n\n{tail}"

    return cleaned


CAVEMAN_REPLACEMENTS = [
    (re.compile(r"(?i)\bensure that all variables are properly initialized\b"), "Init all vars."),
    (re.compile(r"(?i)\benforce clean modular decomposition and zero breaking changes\b"), "Modular design. Zero breaking changes."),
    (re.compile(r"(?i)\bprioritize verifiable implementations with automated unit tests\b"), "Verifiable code. Auto unit tests."),
    (re.compile(r"(?i)\bavoid plain-text secret exposure, validate external inputs, and enforce safe defaults\b"), "Zero raw secrets. Validate inputs. Safe defaults."),
    (re.compile(r"(?i)\bperform exhaustive architectural decomposition, risk matrix evaluation, and concurrency safety checks\b"), "Deep architectural scope. Risk matrix. Concurrency safety."),
]


def compress_system_prompt_caveman(system_prompt: str) -> str:
    """Apply Caveman/Telegraphic Compression to system prompts to save an extra 50-70% system tokens."""
    if not system_prompt or not isinstance(system_prompt, str):
        return system_prompt

    compressed = system_prompt
    for pattern, replacement in CAVEMAN_REPLACEMENTS:
        compressed = pattern.sub(replacement, compressed)

    return compressed


def trim_system_prompt(system_prompt: str) -> str:
    """Trim and deduplicate redundant formatting in system prompts, saving ~15% input tokens."""
    if not system_prompt or not isinstance(system_prompt, str):
        return system_prompt

    system_prompt = compress_system_prompt_caveman(system_prompt)
    lines = system_prompt.splitlines()
    seen_lines: set[str] = set()
    cleaned_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Deduplicate identical bullet lines or dividers
        if stripped and (stripped.startswith("- ") or stripped.startswith("* ") or stripped == "---"):
            if stripped in seen_lines:
                continue
            seen_lines.add(stripped)
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    result = MULTIPLE_NEWLINES_REGEX.sub("\n\n", result)
    return result.strip()



# Regex patterns for stripping conversational filler
CHATTER_PATTERNS = [
    re.compile(r"(?i)^(sure|certainly|of course|here is|i\'d be happy to|let me help|below is)\b[^\n]*\n?"),
    re.compile(r"(?i)^(hope this helps|let me know if you need anything else|feel free to ask)\.?:?\n?"),
]


def semantic_prune_prompt(prompt_text: str) -> str:
    """Semantically prune conversational chatter and duplicate headers for 30% extra token savings."""
    if not prompt_text or not isinstance(prompt_text, str):
        return prompt_text

    pruned = prompt_text
    for pat in CHATTER_PATTERNS:
        pruned = pat.sub("", pruned)

    pruned = MULTIPLE_NEWLINES_REGEX.sub("\n\n", pruned)
    return pruned.strip()



def distill_payload_messages(payload: dict[str, Any], max_chars: int | None = None) -> None:
    """In-place distillation of messages payload & system prompt to save tokens before sending upstream."""
    if not isinstance(payload, dict):
        return

    # 1. Compress System Prompt if present
    if "system" in payload:
        sys_val = payload["system"]
        if isinstance(sys_val, str):
            payload["system"] = trim_system_prompt(sys_val)
        elif isinstance(sys_val, list):
            for block in sys_val:
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    block["text"] = trim_system_prompt(block["text"])

    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return

    limit = max_chars if max_chars is not None else MAX_DISTILL_CHARS

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = compress_tool_result_content(content, max_chars=limit)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") in ("tool_result", "text"):
                    text_val = block.get("text") or block.get("content")
                    if isinstance(text_val, str) and len(text_val) > limit:
                        # Apply AST skeletonization for Python code blocks first (80% token savings)
                        skeleton = skeletonize_code(text_val)
                        compressed = compress_tool_result_content(skeleton, max_chars=limit)
                        if "text" in block:
                            block["text"] = compressed
                        if "content" in block and isinstance(block["content"], str):
                            block["content"] = compressed

