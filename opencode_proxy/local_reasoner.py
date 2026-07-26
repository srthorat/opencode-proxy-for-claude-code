import json
import logging
import urllib.request
from typing import Any

from .config import ENABLE_SMOLLM2_REASONER, SMOLLM2_MODEL, SMOLLM2_URL

logger = logging.getLogger("opencode-proxy.local_reasoner")

PROMPT_TEMPLATE = (
    "You are SmolLM2-135M, an ultra-fast local reasoning model for an AI coding proxy.\n"
    "Analyze the following user prompt to identify intent category, relevant skills/plugins, and engineering role.\n"
    "Categories: [refactor, debugging, docs, security, qa, frontend, planning, general]\n"
    "Available Skills/Plugins: [gstack, superpowers, context7, sequential-thinking, ui-ux-pro-max, anthropic-skills]\n"
    "Available Roles: [role-cto, role-architect, role-principal, role-staff, role-senior, role-qa-architect]\n\n"
    "User prompt: \"{user_prompt}\"\n\n"
    "Respond with ONLY a JSON object:\n"
    "{{\"intent\": \"<category>\", \"skills\": [\"<skill_name>\"], \"role\": \"<role_name_or_empty>\"}}\n"
)


def predict_intent_and_skills_with_smollm2(user_prompt: str, timeout_seconds: float = 0.5) -> dict[str, Any] | None:
    """Send prompt to local SmolLM2-135M model for real-time intent, skill & role prediction (< 15ms).

    Returns dict with keys: 'intent', 'skills', 'role' or None if local model is offline/unreachable.
    """
    if not ENABLE_SMOLLM2_REASONER or not user_prompt or not user_prompt.strip():
        return None

    prompt_input = user_prompt.strip()[:300]
    request_prompt = PROMPT_TEMPLATE.format(user_prompt=prompt_input)

    payload = {
        "model": SMOLLM2_MODEL,
        "prompt": request_prompt,
        "stream": False,
        "options": {
            "num_predict": 50,
            "temperature": 0.1,
        },
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SMOLLM2_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            if resp.status == 200:
                result_bytes = resp.read()
                res_json = json.loads(result_bytes.decode("utf-8"))
                response_text = res_json.get("response", "").strip()

                if "{" in response_text and "}" in response_text:
                    json_str = response_text[response_text.index("{") : response_text.rindex("}") + 1]
                    parsed = json.loads(json_str)
                    intent = parsed.get("intent", "").lower().strip()
                    skills = parsed.get("skills", [])
                    role = parsed.get("role", "").lower().strip()

                    valid_intents = ("refactor", "debugging", "docs", "security", "qa", "frontend", "planning", "general")
                    if intent in valid_intents:
                        logger.info("SmolLM2-135M classified intent: %s | skills: %s | role: %s", intent, skills, role)
                        return {
                            "intent": intent,
                            "skills": skills if isinstance(skills, list) else [],
                            "role": role if role.startswith("role-") else "",
                        }
    except Exception as exc:
        logger.debug("SmolLM2-135M local reasoner unavailable: %s", exc)

    return None


def predict_intent_with_smollm2(user_prompt: str, timeout_seconds: float = 0.5) -> str | None:
    """Backwards-compatible helper returning intent string or None."""
    res = predict_intent_and_skills_with_smollm2(user_prompt, timeout_seconds)
    return res["intent"] if res else None


JUDGE_PROMPT_TEMPLATE = (
    "You are SmolLM2-135M, an ultra-fast local AI Quality Judge Brain for a coding proxy.\n"
    "Compare Response A and Response B for the following user prompt.\n\n"
    "User Prompt: \"{prompt}\"\n\n"
    "Response A:\n{text_a}\n\n"
    "Response B:\n{text_b}\n\n"
    "Which response is higher quality, more complete, and logically sound?\n"
    "Respond with ONLY a JSON object: {{\"winner\": \"A\"}} or {{\"winner\": \"B\"}}\n"
)


def judge_best_response_with_smollm2(prompt: str, text_a: str, text_b: str, timeout_seconds: float = 0.5) -> str:
    """Use SmolLM2-135M as an ultra-fast local AI Judge Brain (< 15ms) to pick the superior response.

    Returns 'A' or 'B'. Defaults to 'A' if local model is offline.
    """
    if not ENABLE_SMOLLM2_REASONER or not text_a or not text_b:
        return "A"

    p_in = prompt.strip()[:200]
    a_in = text_a.strip()[:300]
    b_in = text_b.strip()[:300]

    request_prompt = JUDGE_PROMPT_TEMPLATE.format(prompt=p_in, text_a=a_in, text_b=b_in)
    payload = {
        "model": SMOLLM2_MODEL,
        "prompt": request_prompt,
        "stream": False,
        "options": {"num_predict": 20, "temperature": 0.1},
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SMOLLM2_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            if resp.status == 200:
                result_bytes = resp.read()
                res_json = json.loads(result_bytes.decode("utf-8"))
                response_text = res_json.get("response", "").strip()
                if "{" in response_text and "}" in response_text:
                    json_str = response_text[response_text.index("{") : response_text.rindex("}") + 1]
                    parsed = json.loads(json_str)
                    winner = parsed.get("winner", "A").upper().strip()
                    if winner in ("A", "B"):
                        logger.info("SmolLM2-135M AI Quality Judge selected Winner: Candidate %s", winner)
                        return winner
    except Exception as exc:
        logger.debug("SmolLM2-135M Quality Judge unavailable: %s", exc)

    return "A"

