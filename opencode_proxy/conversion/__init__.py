# Conversion sub-package: Anthropic ↔ OpenAI protocol translation.

# Shared stop-reason mapping — defined once here so both response.py and
# streaming.py import from a single source of truth (P2 #8).
STOP_REASON_MAP: dict[str, str] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
}
