"""
opencode-proxy strix_auditor
─────────────────────────────
Strix Security Auditor Skill: Performs static vulnerability pattern checks
and injects OWASP Top 10 defensive remediation rules into developer prompts.
"""
import logging
import re

logger = logging.getLogger("opencode-proxy.strix_auditor")

SECURITY_KEYWORDS = re.compile(
    r"\b(security|vulnerability|audit|owasp|sqli|xss|ssrf|csrf|jwt|sanitize|patch|exploit|secret|hardening)\b",
    re.I,
)


def is_security_audit_prompt(user_text: str) -> bool:
    """Return True if prompt requires Strix defensive security auditing guidelines."""
    if not user_text or not isinstance(user_text, str):
        return False
    return bool(SECURITY_KEYWORDS.search(user_text))


def get_strix_security_audit_context(user_text: str) -> str:
    """Inject Strix OWASP Top 10 defensive security auditing rules into prompt context."""
    if not is_security_audit_prompt(user_text):
        return ""

    logger.info("Strix Security Auditor Skill auto-activated.")
    return (
        "\n--- STRIX DEFENSIVE SECURITY AUDITOR SKILL ACTIVE ---\n"
        "- OWASP Top 10 Defenses: Enforce parameterized SQL queries (zero string concatenation in queries).\n"
        "- Input Sanitization & XSS: HTML-escape user outputs, validate MIME types, and apply strict CSP headers.\n"
        "- SSRF & Network Hardening: Validate destination URLs against private IP ranges (127.0.0.1, 10.0.0.0/8, 192.168.0.0/16).\n"
        "- Secret Redaction: Zero hardcoded credentials, API keys, or private certificates in code.\n"
        "- Auth & JWT Integrity: Require explicit algorithm pinning (e.g. HS256/RS256) and expiration validation.\n"
        "--- END STRIX SECURITY AUDITOR ---\n"
    )
