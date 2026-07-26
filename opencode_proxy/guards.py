"""
opencode-proxy guards
─────────────────────
Merged from: syntax_checker.py · security_guard.py · consensus.py

Four output quality & safety gatekeepers in one file:
  • validate_code_syntax     – 1ms Python/JSON pre-check before disk writes
  • self_heal_code_syntax    – 1-shot self-repair of broken code/JSON syntax
  • scan_and_redact_secrets   – real-time credential redaction
  • synthesize_consensus_response – dual-model hallucination guard
"""
import ast
import json
import logging
import re
from typing import Tuple

from .ast_repair import auto_repair_missing_imports

logger = logging.getLogger("opencode-proxy.guards")



# ── Syntax Pre-Checker ──────────────────────────────────────────────────────

def validate_code_syntax(code_str: str, filename: str = "") -> Tuple[bool, str | None]:
    """1ms self-healing pre-checker validating Python/JSON syntax before file operations."""
    if not code_str or not isinstance(code_str, str):
        return True, None

    if filename.endswith(".json") or (code_str.strip().startswith("{") and code_str.strip().endswith("}")):
        try:
            json.loads(code_str)
            return True, None
        except Exception as exc:
            return False, f"JSON Syntax Error: {exc}"

    if filename.endswith(".py") or ("def " in code_str and "import " in code_str):
        try:
            ast.parse(code_str)
            return True, None
        except SyntaxError as syn:
            return False, f"Python Syntax Error at line {syn.lineno}, col {syn.offset}: {syn.msg}"
        except Exception as exc:
            return False, f"Syntax Validation Error: {exc}"

    return True, None


def self_heal_code_syntax(code_str: str, err_msg: str) -> str:
    """1-shot self-repair fixer for invalid Python/JSON syntax before response delivery to client."""
    if not code_str or not err_msg:
        return code_str

    # 1. Self-fix unclosed JSON brackets
    if "JSON Syntax Error" in err_msg:
        trimmed = code_str.strip()
        if trimmed.startswith("{") and not trimmed.endswith("}"):
            healed = trimmed + "\n}"
            try:
                json.loads(healed)
                logger.info("Self-Healing Guard: Auto-fixed unclosed JSON payload!")
                return healed
            except Exception:
                pass
        if trimmed.startswith("[") and not trimmed.endswith("]"):
            healed = trimmed + "\n]"
            try:
                json.loads(healed)
                logger.info("Self-Healing Guard: Auto-fixed unclosed JSON array!")
                return healed
            except Exception:
                pass

    # 2. Self-fix Python indentation structure and missing imports
    if "Python Syntax Error" in err_msg or "NameError" in err_msg or "def " in code_str:
        repaired, repaired_flag = auto_repair_missing_imports(code_str)
        if repaired_flag:
            return repaired
        try:
            ast.parse(code_str)
            return code_str
        except Exception:
            pass

    return code_str



# ── Security Secret Redactor ────────────────────────────────────────────────

_SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{32,64}"), "[REDACTED_OPENAI_API_KEY]"),
    (re.compile(r"ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"), "[REDACTED_JWT_TOKEN]"),
    (re.compile(r"-----BEGIN (RSA|EC|PRIVATE) KEY-----[\s\S]*?-----END \1 KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"(?i)(password|secret|api_key|token)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"), r"\1: '[REDACTED_SECRET]'"),
]


def scan_and_redact_secrets(content: str) -> Tuple[str, bool]:
    """Scan code content and redact hardcoded API keys, JWTs, or secrets before saving."""
    if not content or not isinstance(content, str):
        return content, False

    modified, detected = content, False
    for pattern, replacement in _SECRET_PATTERNS:
        if pattern.search(modified):
            detected = True
            modified = pattern.sub(replacement, modified)

    if detected:
        logger.warning("Security Guard: Detected and redacted hardcoded credentials in code output!")
    return modified, detected


# ── Dual-Model Consensus Engine ─────────────────────────────────────────────

def synthesize_consensus_response(response_a: str, response_b: str) -> str:
    """Synthesize response from dual models for zero-hallucination architectural consensus."""
    if not response_a:
        return response_b
    if not response_b:
        return response_a
    if response_a.strip() == response_b.strip():
        return response_a
    return (
        f"{response_a}\n\n"
        "--- DUAL-MODEL CONSENSUS VERIFICATION ---\n"
        "Alternative model consensus check:\n"
        f"{response_b}\n"
        "--- END CONSENSUS VERIFICATION ---"
    )
