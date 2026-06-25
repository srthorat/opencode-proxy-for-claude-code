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
PORT: int = int(os.getenv("PORT", "8080"))
# Optional inbound auth — if set, every request must carry "Authorization: Bearer <key>"
PROXY_API_KEY: str | None = os.getenv("PROXY_API_KEY")
# Direct provider bypass — routes direct:<model> straight to a non-OpenCode endpoint
DIRECT_URL: str = os.getenv("DIRECT_URL", "").rstrip("/")
DIRECT_KEY: str | None = os.getenv("DIRECT_KEY")

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
    "trivial": "big-pickle",            # one-liners, quick facts, tiny scripts
    "simple":  "north-mini-code-free",   # basic code, short functions, easy debug
    "fast":    "deepseek-v4-flash-free", # fast general free fallback
    "general": "mimo-v2.5-free",         # free general quality option
}

# Go paid tier (zen/go/v1) — best-in-class per category.
# Model IDs from https://opencode.ai/docs/go/
# Anthropic-compat (/v1/messages):      minimax-m3, minimax-m2.7, minimax-m2.5,
#                                        qwen3.7-max, qwen3.7-plus, qwen3.6-plus
# OpenAI-compat (/v1/chat/completions): kimi-k2.7, kimi-k2.6, deepseek-v4-pro,
#                                        deepseek-v4-flash, mimo-v2.5, mimo-v2.5-pro,
#                                        glm-5.2, glm-5.1
CODER_MAP_GO: dict[str, str] = {
    "code":      "opencode-go/kimi-k2.7-code",   # complex code, algorithms, multi-file debug
    "reasoning": "opencode-go/deepseek-v4-pro",   # architecture, math, analysis, step-by-step
    "long":      "opencode-go/minimax-m3",        # large context, documents, summarization
    "creative":  "opencode-go/qwen3.7-plus",      # writing, creative, translation
    "agent":     "opencode-go/mimo-v2.5-pro",     # multi-step agentic, tool-use, planning
    "general":   "opencode-go/qwen3.7-max",       # everything else — high quality default
    "fast":      "opencode-go/deepseek-v4-flash", # quick go-tier tasks
}

# Go-all tier includes all models, assigning GLM-5.2 to general and GLM-5.1 to fast
CODER_MAP_GO_ALL: dict[str, str] = {
    # Level-based category mappings to cover all 14 models
    "code:3":            "opencode-go/kimi-k2.7-code",
    "code:2":            "opencode-go/kimi-k2.6",

    "reasoning:3":       "opencode-go/deepseek-v4-pro",
    "reasoning:2":       "opencode-go/deepseek-v4-flash",

    "long:3":            "opencode-go/minimax-m3",
    "long:2":            "opencode-go/minimax-m2.7",
    "long:1":            "opencode-go/minimax-m2.5",

    "creative:3":        "opencode-go/qwen3.7-plus",
    "creative:2":        "opencode-go/qwen3.6-plus",

    "agent:3":           "opencode-go/mimo-v2.5-pro",
    "agent:2":           "opencode-go/mimo-v2.5",

    "general:3":         "opencode-go/qwen3.7-max",
    "general:2":         "opencode-go/glm-5.2",
    "general:1":         "opencode-go/glm-5.1",

    "fast:3":            "opencode-go/deepseek-v4-flash",
    "fast:2":            "opencode-go/glm-5.1",

    # Category fallbacks (for compatibility or keyword fallbacks)
    "code":              "opencode-go/kimi-k2.7-code",
    "reasoning":         "opencode-go/deepseek-v4-pro",
    "long":              "opencode-go/minimax-m3",
    "creative":          "opencode-go/qwen3.7-plus",
    "agent":             "opencode-go/mimo-v2.5-pro",
    "general":           "opencode-go/qwen3.7-max",
    "fast":              "opencode-go/deepseek-v4-flash",
}


# ---------------------------------------------------------------------------
# Protocol detection
# ---------------------------------------------------------------------------
# Models that accept Anthropic /v1/messages format directly.
_ANTHROPIC_COMPAT_MODELS = {
    "minimax-m3", "minimax-m2.7", "minimax-m2.5",
    "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
    "opencode-go/minimax-m3", "opencode-go/minimax-m2.7", "opencode-go/minimax-m2.5",
    "opencode-go/qwen3.7-max", "opencode-go/qwen3.7-plus", "opencode-go/qwen3.6-plus",
}
