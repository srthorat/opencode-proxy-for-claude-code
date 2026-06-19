import hashlib
import os
import json
import logging
from functools import lru_cache
from typing import Optional

from client import get_client
from config import (
    CODER_MAP_FREE,
    CODER_MAP_GO,
    UPSTREAM_URL,
    UPSTREAM_API_KEY,
    MODEL_MAP,
    DIRECT_URL,
    DIRECT_KEY,
)

logger = logging.getLogger("opencode-proxy")

# ---------------------------------------------------------------------------
# P1 #7: In-process classifier result cache
# ---------------------------------------------------------------------------

_clf_cache: dict[str, tuple[str, str]] = {}
_CLF_CACHE_MAX = 256


CLASSIFIER_SYSTEM = """You are a query router. Reply with JSON only — no explanation, no markdown.

Pick tier and category:
  tier "free"  → trivial or simple tasks only
  tier "go"    → everything else

Categories (pick exactly one):
  trivial   = greetings, yes/no, one-word answers, fill-in-blank
  simple    = basic code under 20 lines, single function, easy fix
  code      = complex algorithms, multi-file debug, data structures, system code
  reasoning = math, architecture tradeoffs, analysis, step-by-step proofs
  long      = summarize docs, translate, output >500 words
  creative  = blog posts, stories, poems, marketing copy
  agent     = multi-step pipelines, automation plans, tool-use workflows
  general   = Q&A, explanations, comparisons not covered above

Output format (JSON, nothing else):
{"tier":"free","category":"trivial"}"""


def _extract_text(messages: list) -> str:
    parts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return " ".join(parts)


# P1 #7: lru_cache on pure keyword classifier — avoids re-scoring identical text.
@lru_cache(maxsize=1024)
def _keyword_fallback(text: str, num_turns: int) -> tuple[str, str]:
    """Instant local fallback — returns (tier, category)."""
    low = text.lower()
    chars = len(text)
    has_block = "```" in text
    code_hits = sum(
        1 for w in (
            "def ", "class ", "function", "debug", "error", "bug",
            "implement", "refactor", "sql", "regex", "algorithm",
            "dockerfile", "import ", "module", "api", "endpoint",
        )
        if w in low
    )
    if has_block or code_hits >= 2:
        return "go", "code"
    if any(w in low for w in ("explain", "analyze", "compare", "tradeoff", "architecture",
                               "math", "proof", "calculate", "step by step")):
        return "go", "reasoning"
    if chars > 3000 or num_turns > 8:
        return "go", "long"
    if any(w in low for w in ("write a", "blog", "story", "essay", "creative", "poem")):
        return "go", "creative"
    if any(w in low for w in ("plan", "pipeline", "workflow", "agent", "automate", "tool")):
        return "go", "agent"
    if chars < 150 and num_turns <= 2:
        return "free", "trivial"
    if chars < 400 and num_turns <= 3:
        return "free", "simple"
    return "go", "general"


def get_fallbacks(model_name: str) -> list[str]:
    """Return the ordered fallback model list for model_name, or [] if none configured."""
    entry = MODEL_MAP.get(model_name)
    if isinstance(entry, dict):
        return list(entry.get("fallbacks", []))
    return []


def map_claude_model_name(model_name: str) -> str:
    """Map claude-* model names to proxy routing tokens.

    Applied when the client sends a claude-* model that is NOT explicitly in MODEL_MAP:
      claude-haiku-*  → free-auto  (light tasks, lower cost)
      claude-opus-*   → go-auto    (flagship — map to best go model)
      claude-sonnet-* → go-auto    (default Claude Code model)
      everything else → go-auto    (safe fallback for unknown claude-*)

    Returns the model_name unchanged if it doesn't start with 'claude-' or is
    explicitly listed in MODEL_MAP.
    """
    if not isinstance(model_name, str):
        return model_name
    model_lower = model_name.strip().lower()
    if not model_lower.startswith("claude-"):
        return model_name
    if model_name in MODEL_MAP:
        return model_name  # explicitly mapped — don't override
    if "haiku" in model_lower:
        return "free-auto"
    return "go-auto"


# ---------------------------------------------------------------------------
# P4 #24: URL validation for MODEL_MAP entries
# ---------------------------------------------------------------------------

def _is_safe_url(url: str) -> bool:
    """Return True if url is a valid http/https URL (non-empty, correct scheme).

    Internal Docker network URLs are legitimate for this proxy — we do NOT
    block RFC-1918 addresses.  Only the URL scheme is validated.
    """
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def resolve_model_config(name: str):
    """Return a tuple (upstream_model, upstream_url, upstream_api_key, role).

    MODEL_MAP values may be:
      - a string: upstream model name
      - an object: {"model":..., "url":..., "api_key":..., "role":...}

    Special token for env var: values beginning with "env:" will be read from environment.
    If url value equals the literal "OPENCODE_URL" or is empty, the global UPSTREAM_URL is used.
    """
    if not isinstance(name, str):
        return name, UPSTREAM_URL, UPSTREAM_API_KEY, None

    key = name.strip()

    # direct:<model> — bypass OpenCode entirely, forward to DIRECT_URL with DIRECT_KEY
    if key.startswith("direct:"):
        upstream_model = key[len("direct:"):].strip()
        if not upstream_model:
            logger.warning(
                "direct: prefix used with empty model name — request will likely fail upstream"
            )
        if not DIRECT_URL:
            logger.warning(
                "direct:%s requested but DIRECT_URL is not set — falling back to UPSTREAM_URL",
                upstream_model,
            )
        return upstream_model, DIRECT_URL or UPSTREAM_URL, DIRECT_KEY or UPSTREAM_API_KEY, "direct"

    entry = MODEL_MAP.get(key)
    upstream_model = key.replace(" ", "-")
    upstream_url = UPSTREAM_URL
    upstream_api_key = UPSTREAM_API_KEY
    role = None

    if entry is None:
        return upstream_model, upstream_url, upstream_api_key, role

    # if mapping is a simple string, use it as model name
    if isinstance(entry, str):
        upstream_model = entry
        return upstream_model, upstream_url, upstream_api_key, role

    # otherwise expect a dict
    if isinstance(entry, dict):
        role = entry.get("role")

        # model override
        if entry.get("model"):
            upstream_model = entry.get("model")

        # url handling: allow literal placeholders
        url_val = entry.get("url")
        if isinstance(url_val, str) and url_val:
            if url_val.startswith("env:"):
                envname = url_val.split("env:", 1)[1]
                upstream_url = os.getenv(envname, UPSTREAM_URL)
            elif url_val == "OPENCODE_URL":
                upstream_url = UPSTREAM_URL
            elif not _is_safe_url(url_val):
                # P4 #24: reject URLs that don't start with http:// or https://
                logger.warning(
                    "MODEL_MAP entry %r has invalid url %r (must start with http:// or "
                    "https://) — using UPSTREAM_URL",
                    key, url_val,
                )
                # upstream_url stays as UPSTREAM_URL
            else:
                upstream_url = url_val

        # api_key handling
        key_val = entry.get("api_key")
        if isinstance(key_val, str) and key_val:
            if key_val.startswith("env:"):
                envname = key_val.split("env:", 1)[1]
                upstream_api_key = os.getenv(envname, upstream_api_key)
            else:
                upstream_api_key = key_val

    return upstream_model, upstream_url, upstream_api_key, role


async def auto_select_model(
    messages: list,
    forced_tier: Optional[str] = None,
    has_tools: bool = False,
) -> str:
    """Select the best upstream model for the given conversation.

    Stage 1 — north-mini-code-free analyses the query (tier + category).
    Stage 2 — pick from CODER_MAP_FREE or CODER_MAP_GO.
    Falls back to keyword scoring if LLM call fails or times out (3 s).

    forced_tier: "free" → always use free-tier models (free-auto mode).
                 "go"   → always use go-tier models (go-auto mode).
                 None   → auto-detect tier from query (auto mode).
    has_tools:   True when the request payload includes a `tools` array
                 (Claude Code agent mode). Triggers agent mode detection.
    """
    text = _extract_text(messages)
    num_turns = len(messages)
    tier, category = "go", "general"  # safe default
    method = "keyword"

    # ── Agent mode detection ─────────────────────────────────────────────────
    # Takes priority over all other classification. When the client sent a tools
    # array AND the conversation already contains tool_use / tool_result blocks,
    # this is an agentic loop. Route to the dedicated agent model.
    if has_tools:
        _tool_block_count = sum(
            1 for msg in messages
            for block in (
                msg.get("content") if isinstance(msg.get("content"), list) else []
            )
            if isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result")
        )
        if _tool_block_count >= 2:  # at least one completed tool-call round
            _eff_tier = forced_tier or "go"
            if _eff_tier == "go":
                chosen = CODER_MAP_GO["agent"]
                logger.info(
                    "auto-router: agent mode (%d tool blocks) → %s", _tool_block_count, chosen
                )
            else:
                # free tier has no dedicated agent model — use best free option
                chosen = CODER_MAP_FREE["general"]
                logger.info(
                    "auto-router: agent mode free tier (%d tool blocks) → %s",
                    _tool_block_count,
                    chosen,
                )
            return chosen

    # Fast pre-check: code blocks or strong code signals skip LLM entirely
    low = text.lower()
    if "```" in text or sum(
        1 for w in (
            "def ", "class ", "function", "algorithm",
            "implement", "refactor", "debug", "traceback",
            "leetcode", "quicksort", "recursion",
        )
        if w in low
    ) >= 2:
        if forced_tier == "free":
            chosen = CODER_MAP_FREE.get("simple", CODER_MAP_FREE["simple"])
            logger.info("auto-router[precheck]: forced_tier=free category=code → %s", chosen)
            return chosen
        logger.info("auto-router[precheck]: tier=go category=code → kimi-k2.7-code")
        return CODER_MAP_GO["code"]

    # ── Stage 1: LLM classification via north-mini-code-free ────────────────
    # P1 #7: Check the in-process cache before making an LLM call.
    text_short = text[:600]
    cache_key = hashlib.md5(text_short.encode(), usedforsecurity=False).hexdigest()

    if cache_key in _clf_cache:
        tier, category = _clf_cache[cache_key]
        method = "cache"
    else:
        try:
            classifier = "north-mini-code-free"
            _, clf_url, clf_key, _ = resolve_model_config(classifier)

            # P0 #3: Build classifier URL with /v1 dedup — matches the logic in
            # _build_target_url so it works whether clf_url already has /v1 or not.
            clf_base = clf_url.rstrip("/")
            if clf_base.endswith("/v1"):
                clf_path = "/chat/completions"
            else:
                clf_path = "/v1/chat/completions"
            classifier_url = clf_base + clf_path

            # P1 #5: Reuse the module-level shared client instead of creating a
            # fresh httpx.AsyncClient for every routing decision.
            client = await get_client()
            resp = await client.post(
                classifier_url,
                headers={
                    "Authorization": f"Bearer {clf_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": classifier,
                    "messages": [
                        {"role": "system", "content": CLASSIFIER_SYSTEM},
                        {"role": "user",   "content": text_short},
                    ],
                    "max_tokens": 30,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=3.0,
            )
            if resp.status_code == 200:
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                # parse first JSON object in the response
                start, end = raw.find("{"), raw.rfind("}")
                if start != -1 and end != -1:
                    parsed = json.loads(raw[start:end + 1])
                    tier     = parsed.get("tier", tier).strip().lower()
                    category = parsed.get("category", category).strip().lower()
                    method   = "llm"
                    # P1 #7: Store successful classification in cache.
                    if len(_clf_cache) >= _CLF_CACHE_MAX:
                        oldest = next(iter(_clf_cache))
                        del _clf_cache[oldest]
                    _clf_cache[cache_key] = (tier, category)
        except Exception as exc:
            logger.debug("classifier failed, using keyword fallback: %s", exc)
            # method stays "keyword" — the block below will call _keyword_fallback once

    if method == "keyword":
        tier, category = _keyword_fallback(text, num_turns)

    # Apply forced tier override (free-auto / go-auto)
    if forced_tier:
        tier = forced_tier

    # ── Stage 2: pick model from the right map ───────────────────────────────
    if tier == "free":
        chosen = CODER_MAP_FREE.get(category, CODER_MAP_FREE["simple"])
    else:
        chosen = CODER_MAP_GO.get(category, CODER_MAP_GO["general"])

    logger.info(
        "auto-router[%s]: tier=%s category=%s → %s", method, tier, category, chosen
    )
    return chosen
