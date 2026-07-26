"""
opencode-proxy prompt_tuner
────────────────────────────
Self-Optimizing System Prompt Auto-Tuner: Uses SmolLM2-135M as an ultra-fast
AI reasoning brain (< 15ms) to dynamically generate tailored, prompt-specific
system prompt tuning rules.
"""
import json
import logging
import urllib.request
from typing import Any

from .config import ENABLE_SMOLLM2_REASONER, SMOLLM2_MODEL, SMOLLM2_URL

logger = logging.getLogger("opencode-proxy.prompt_tuner")

INTENT_OPTIMIZATIONS = {
    "refactor": "\n[Auto-Tuner Guideline: Prioritize modular decomposition, clean functions under 50 lines, and zero breaking changes.]",
    "debugging": "\n[Auto-Tuner Guideline: Enforce step-by-step root cause verification before proposing code edits.]",
    "security": "\n[Auto-Tuner Guideline: Enforce input sanitization, zero hardcoded credentials, and safe default permissions.]",
    "qa": "\n[Auto-Tuner Guideline: Include comprehensive edge case and boundary failure assertions.]",
    "frontend": "\n[Auto-Tuner Guideline: Enforce modern responsive layout, Glassmorphism design tokens, and ARIA 4.5:1 contrast.]",
}

PROMPT_TUNER_TEMPLATE = (
    "You are SmolLM2-135M, an ultra-fast local AI Prompt Auto-Tuner for a coding proxy.\n"
    "Generate ONE concise (10-15 word) architectural enforcement rule for this coding prompt:\n\n"
    "User Prompt: \"{user_prompt}\"\n"
    "Intent Category: {intent}\n\n"
    "Respond with ONLY a JSON object: {{\"guideline\": \"<rule_text>\"}}\n"
)


def tune_system_prompt_for_intent(system_prompt: str, intent: str, user_prompt: str = "") -> str:
    """Use SmolLM2-135M as a real-time AI Prompt Auto-Tuner (< 15ms) to generate tailored, prompt-specific system guidelines."""
    if not system_prompt or not isinstance(system_prompt, str):
        return system_prompt

    if ENABLE_SMOLLM2_REASONER and user_prompt:
        try:
            req_prompt = PROMPT_TUNER_TEMPLATE.format(user_prompt=user_prompt.strip()[:200], intent=intent)
            payload = {
                "model": SMOLLM2_MODEL,
                "prompt": req_prompt,
                "stream": False,
                "options": {"num_predict": 25, "temperature": 0.1},
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                SMOLLM2_URL,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    result_bytes = resp.read()
                    res_json = json.loads(result_bytes.decode("utf-8"))
                    response_text = res_json.get("response", "").strip()
                    if "{" in response_text and "}" in response_text:
                        json_str = response_text[response_text.index("{") : response_text.rindex("}") + 1]
                        parsed = json.loads(json_str)
                        guideline = parsed.get("guideline", "").strip()
                        if guideline:
                            logger.info("SmolLM2 AI Prompt Auto-Tuner generated custom rule: %s", guideline)
                            return system_prompt + f"\n\n[SmolLM2 Auto-Tuned Rule: {guideline}]"
        except Exception as exc:
            logger.debug("Prompt Auto-Tuner SmolLM2 offline: %s", exc)

    # Baseline fallback if SmolLM2 offline
    tuning_rule = INTENT_OPTIMIZATIONS.get(intent, "")
    if tuning_rule and tuning_rule not in system_prompt:
        logger.info("Prompt Auto-Tuner: Applied baseline optimization rule for intent '%s'", intent)
        return system_prompt + tuning_rule

    return system_prompt
