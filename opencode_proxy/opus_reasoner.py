"""
opencode-proxy opus_reasoner
──────────────────────────────
Opus-Style Multi-Pass Chain-of-Thought Engine: Performs Pass 1 Architectural
Decomposition & Risk Matrix before Pass 2 Code Generation for Opus-tier reasoning.
"""
import logging
import re

logger = logging.getLogger("opencode-proxy.opus_reasoner")

COMPLEX_PATTERNS = re.compile(r"\b(architect|refactor|design|rewrite|security|audit|leak|system|pipeline|database)\b", re.I)


def is_opus_reasoning_required(user_text: str) -> bool:
    """Return True if prompt requires Opus-tier multi-pass chain-of-thought."""
    if not user_text or not isinstance(user_text, str):
        return False
    return len(user_text) > 80 or bool(COMPLEX_PATTERNS.search(user_text))


def generate_opus_pass1_plan(user_text: str) -> str:
    """Generate Pass 1 Architectural Plan & Risk Matrix to guide Pass 2 code generation."""
    if not is_opus_reasoning_required(user_text):
        return ""

    logger.info("Opus Reasoner: Generated Pass 1 Architectural Decomposition Plan.")
    return (
        "\n--- OPUS-STYLE MULTI-PASS REASONING PLAN (PASS 1 DECOMPOSITION) ---\n"
        "1. Architectural Scope: Identify module boundaries and dependency contracts.\n"
        "2. Risk Matrix: Evaluate race conditions, memory leaks, and breaking API changes.\n"
        "3. Boundary Conditions: Define zero-value, empty-string, and exception failure paths.\n"
        "4. Execution Requirement: Write modular, self-documenting code passing all unit assertions.\n"
        "--- END OPUS PASS 1 PLAN ---\n"
    )
