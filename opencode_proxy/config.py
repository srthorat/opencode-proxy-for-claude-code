from __future__ import annotations

import json
import logging
import os
import pathlib

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell-exported env vars

logger = logging.getLogger("opencode-proxy")

UPSTREAM_URL: str = os.getenv("UPSTREAM_URL", "https://api.opencode.ai").rstrip("/")
UPSTREAM_API_KEY: str | None = os.getenv("OPENCODE_API_KEY")
OPENCODE_FREE_URL: str = os.getenv("OPENCODE_FREE_URL", "").rstrip("/")

# Ordered list of outbound proxies for IP rotation (comma-separated, e.g. "http://proxy1,http://proxy2")
OUTBOUND_PROXIES: list[str] = [
    p.strip() for p in os.getenv("OUTBOUND_PROXIES", "").split(",") if p.strip()
]

# ProxyScrape URL to automatically scrape free proxies filtered by desired countries (US, India, Singapore)
AUTO_PROXY_URL: str = os.getenv(
    "AUTO_PROXY_URL", 
    "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&country=us,in,sg&protocol=http&timeout=10000"
)



PORT: int = int(os.getenv("PORT", "8080"))
# Optional inbound auth — if set, every request must carry "Authorization: Bearer <key>"
PROXY_API_KEY: str | None = os.getenv("PROXY_API_KEY")
# Direct provider bypass — routes direct:<model> straight to a non-OpenCode endpoint
DIRECT_URL: str = os.getenv("DIRECT_URL", "").rstrip("/")
DIRECT_KEY: str | None = os.getenv("DIRECT_KEY")


# Dedicated key for the go (paid) tier — isolated from the free-tier key pool.
# Set OPENCODE_GO_API_KEY in .env; if absent, falls back to UPSTREAM_API_KEY.
GO_API_KEY: str | None = os.getenv("OPENCODE_GO_API_KEY") or UPSTREAM_API_KEY

# Ordered list of OpenCode API keys for free-auto key rotation.
# Add more free keys by appending OPENCODE_API_KEY_2 … _10 in .env.
UPSTREAM_API_KEYS: list[str] = [
    k
    for k in [
        os.getenv("OPENCODE_API_KEY"),
        os.getenv("OPENCODE_API_KEY_2"),
        os.getenv("OPENCODE_API_KEY_3"),
        os.getenv("OPENCODE_API_KEY_4"),
        os.getenv("OPENCODE_API_KEY_5"),
        os.getenv("OPENCODE_API_KEY_6"),
        os.getenv("OPENCODE_API_KEY_7"),
        os.getenv("OPENCODE_API_KEY_8"),
        os.getenv("OPENCODE_API_KEY_9"),
        os.getenv("OPENCODE_API_KEY_10"),
    ]
    if k
]




# The four free-auto models that participate in key-pool rotation.
FREE_AUTO_MODELS: frozenset[str] = frozenset(
    {
        "big-pickle",
        "north-mini-code-free",
        "deepseek-v4-flash-free",
        "mimo-v2.5-free",
    }
)


# MODEL_MAP: prefer MODEL_MAP env var (runtime override) then models.json
_MODEL_MAP_JSON: str = os.getenv("MODEL_MAP", "")
MODEL_MAP: dict[str, str | dict[str, str]]
if _MODEL_MAP_JSON:
    try:
        MODEL_MAP = json.loads(_MODEL_MAP_JSON)
    except json.JSONDecodeError as e:
        MODEL_MAP = {}
        logger.warning("MODEL_MAP env var contains invalid JSON (ignored): %s", e)
else:
    _models_file = pathlib.Path(__file__).parent / "models.json"
    try:
        MODEL_MAP = json.loads(_models_file.read_text())
    except FileNotFoundError:
        MODEL_MAP = {}
        logger.warning("models.json not found and MODEL_MAP env var not set — model lookups will fall through")
    except json.JSONDecodeError as e:
        MODEL_MAP = {}
        logger.warning("models.json contains invalid JSON (ignored): %s", e)


# ---------------------------------------------------------------------------
# Two named coder maps
# ---------------------------------------------------------------------------

# Free tier (zen/v1) — fast, cheap, used for simple/trivial tasks
# Note: free-tier models use OpenAI-compat /chat/completions endpoint.
CODER_MAP_FREE: dict[str, str] = {
    "trivial": "big-pickle",  # one-liners, quick facts, tiny scripts
    "simple": "north-mini-code-free",  # basic code, short functions, easy debug
    "fast": "deepseek-v4-flash-free",  # fast general free fallback
    "general": "mimo-v2.5-free",  # free general quality option
}

# Free global tier (free-global/v1) — open-source/global providers only.
CODER_MAP_FREE_GLOBAL: dict[str, str] = {
    "tier1": "mimo-v2.5-free",
    "code": "north-mini-code-free",
    "creative": "mimo-v2.5-free",
    "image+reasoning": "mimo-v2.5-free",
    "general": "mimo-v2.5-free",
    "long": "mimo-v2.5-free",
    "reasoning": "mimo-v2.5-free",
}

# Go paid tier (zen/go/v1) — best-in-class per category.
CODER_MAP_GO: dict[str, str] = {
    "code": "north-mini-code-free",
    "reasoning": "mimo-v2.5-free",
    "long": "mimo-v2.5-free",
    "creative": "mimo-v2.5-free",
    "agent": "mimo-v2.5-free",
    "general": "mimo-v2.5-free",
    "fast": "deepseek-v4-flash-free",
}

# Go-all tier includes all remaining models
CODER_MAP_GO_ALL: dict[str, str] = {
    # Level-based category mappings to cover remaining models
    "code:4": "north-mini-code-free",
    "code:3": "north-mini-code-free",
    "code:2": "north-mini-code-free",
    "reasoning:4": "mimo-v2.5-free",
    "reasoning:3": "mimo-v2.5-free",
    "reasoning:2": "mimo-v2.5-free",
    "long:3": "mimo-v2.5-free",
    "long:2": "mimo-v2.5-free",
    "long:1": "mimo-v2.5-free",
    "long:0": "mimo-v2.5-free",
    "creative:3": "mimo-v2.5-free",
    "creative:2": "mimo-v2.5-free",
    "agent:3": "mimo-v2.5-free",
    "agent:2": "mimo-v2.5-free",
    "general:4": "mimo-v2.5-free",
    "general:3": "mimo-v2.5-free",
    "general:2": "mimo-v2.5-free",
    "general:1": "mimo-v2.5-free",
    "fast:3": "deepseek-v4-flash-free",
    "fast:2": "deepseek-v4-flash-free",
    # Category fallbacks (for compatibility or keyword fallbacks)
    "code": "north-mini-code-free",
    "reasoning": "mimo-v2.5-free",
    "long": "mimo-v2.5-free",
    "creative": "mimo-v2.5-free",
    "agent": "mimo-v2.5-free",
    "general": "mimo-v2.5-free",
    "fast": "deepseek-v4-flash-free",
}


# Models that accept Anthropic /v1/messages format directly.
_ANTHROPIC_COMPAT_MODELS = {
    "minimax-m3:cloud",
    "kimi-k2.7-code:cloud",
}


def is_anthropic_compat(model_name: str, target_url: str = "") -> bool:
    """Return True if model speaks native Anthropic Messages format (no OpenAI conversion needed)."""
    if not model_name:
        return False
    if model_name in _ANTHROPIC_COMPAT_MODELS:
        return True
    if ":" in model_name or model_name.endswith(":cloud"):
        return True
    return False

