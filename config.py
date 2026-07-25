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
# Keys 1-4 only — KEY_5 is reserved as the go-tier key (OPENCODE_GO_API_KEY).
# Add more free keys by appending OPENCODE_API_KEY_2 … _4 in .env.
UPSTREAM_API_KEYS: list[str] = [
    k
    for k in [
        os.getenv("OPENCODE_API_KEY"),
        os.getenv("OPENCODE_API_KEY_2"),
        os.getenv("OPENCODE_API_KEY_3"),
        os.getenv("OPENCODE_API_KEY_4"),
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
# All entries are genuinely free and verified stable (no intermittent 429s).
# No OpenCode go-subscription, no direct ZAI, no OpenRouter gpt-oss (rate-limited).
# For GLM via OpenCode subscription, use the go tier (opencode-go/glm-5.2).
CODER_MAP_FREE_GLOBAL: dict[str, str] = {
    "tier1": "free-global/cohere/north-mini-code-free",  # core free global tier (OpenRouter, 256K)
    "code": "free-global/cohere/north-mini-code-free",  # code + reasoning
    "creative": "free-global/google/gemma-4-31b-it",  # creative tasks (gpt-oss dropped: rate-limited)
    "image+reasoning": "free-global/google/gemma-4-31b-it",  # image understanding + reasoning
    "general": "free-global/cohere/north-mini-code-free",  # general default
    "long": "free-global/cohere/north-mini-code-free",  # 256K context for long text
    "reasoning": "free-global/google/gemma-4-31b-it",  # reasoning-capable, free
}

# Go paid tier (zen/go/v1) — best-in-class per category.
# Model IDs from https://opencode.ai/docs/go/
# Anthropic-compat (/v1/messages):      minimax-m3, minimax-m2.7, minimax-m2.5,
#                                        qwen3.7-max, qwen3.7-plus, qwen3.6-plus
# OpenAI-compat (/v1/chat/completions): grok-4.5, kimi-k3, kimi-k2.7-code, kimi-k2.6,
#                                        deepseek-v4-pro, deepseek-v4-flash, mimo-v2.5,
#                                        mimo-v2.5-pro, glm-5.2, glm-5.1
CODER_MAP_GO: dict[str, str] = {
    "code": "opencode-go/kimi-k3",  # flagship code, algorithms, multi-file debug
    "reasoning": "opencode-go/grok-4.5",  # flagship reasoning, math, architecture tradeoffs
    "long": "opencode-go/minimax-m3",  # large context, documents, summarization
    "creative": "opencode-go/qwen3.7-plus",  # writing, creative, translation
    "agent": "opencode-go/mimo-v2.5-pro",  # multi-step agentic, tool-use, planning
    "general": "opencode-go/grok-4.5",  # everything else — flagship general default
    "fast": "opencode-go/kimi-k3",  # quick go-tier tasks
}

# Go-all tier includes all remaining models
CODER_MAP_GO_ALL: dict[str, str] = {
    # Level-based category mappings to cover remaining models
    "code:4": "opencode-go/kimi-k3",
    "code:3": "opencode-go/kimi-k3",
    "code:2": "opencode-go/kimi-k3",
    "reasoning:4": "opencode-go/grok-4.5",
    "reasoning:3": "opencode-go/grok-4.5",
    "reasoning:2": "opencode-go/grok-4.5",
    "long:3": "opencode-go/minimax-m3",
    "long:2": "opencode-go/minimax-m3",
    "long:1": "opencode-go/minimax-m3",
    "long:0": "opencode-go/minimax-m3",
    "creative:3": "opencode-go/qwen3.7-plus",
    "creative:2": "opencode-go/qwen3.7-plus",
    "agent:3": "opencode-go/mimo-v2.5-pro",
    "agent:2": "opencode-go/mimo-v2.5-pro",
    "general:4": "opencode-go/grok-4.5",
    "general:3": "opencode-go/grok-4.5",
    "general:2": "opencode-go/grok-4.5",
    "general:1": "opencode-go/grok-4.5",
    "fast:3": "opencode-go/kimi-k3",
    "fast:2": "opencode-go/kimi-k3",
    # Category fallbacks (for compatibility or keyword fallbacks)
    "code": "opencode-go/kimi-k3",
    "reasoning": "opencode-go/grok-4.5",
    "long": "opencode-go/minimax-m3",
    "creative": "opencode-go/qwen3.7-plus",
    "agent": "opencode-go/mimo-v2.5-pro",
    "general": "opencode-go/grok-4.5",
    "fast": "opencode-go/kimi-k3",
}


# ---------------------------------------------------------------------------
# Protocol detection
# ---------------------------------------------------------------------------
# Models that accept Anthropic /v1/messages format directly.
_ANTHROPIC_COMPAT_MODELS = {
    "minimax-m3",
    "qwen3.7-plus",
    "opencode-go/minimax-m3",
    "opencode-go/qwen3.7-plus",
}
