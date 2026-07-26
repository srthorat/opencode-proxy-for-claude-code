"""
opencode-proxy api_contract
────────────────────────────
Microservice API Contract Skill: Validates OpenAPI 3.0, Protobuf, and gRPC
schemas across microservices for strict backward compatibility.
"""
import logging
import re

logger = logging.getLogger("opencode-proxy.api_contract")

CONTRACT_PATTERNS = re.compile(r"\b(openapi|swagger|protobuf|proto|grpc|schema|endpoint|contract)\b", re.I)


def is_contract_prompt(user_text: str) -> str | None:
    """Return True if prompt involves API contract schemas."""
    if not user_text or not isinstance(user_text, str):
        return None
    return "active" if CONTRACT_PATTERNS.search(user_text) else None


def get_api_contract_context(user_text: str) -> str:
    """Inject Microservice API Contract guidelines into prompt context."""
    if not is_contract_prompt(user_text):
        return ""

    logger.info("Microservice API Contract Skill auto-activated.")
    return (
        "\n--- MICROSERVICE API CONTRACT SKILL ACTIVE ---\n"
        "- Backwards Compatibility: Never break existing field tag numbers in Protobuf or required parameters in OpenAPI.\n"
        "- Schema Validation: Enforce strict type validation, enum boundary checks, and explicit error status codes.\n"
        "- Versioning Strategy: Use URI versioning (/v1/, /v2/) or header versioning to preserve client contracts.\n"
        "--- END API CONTRACT SKILL ---\n"
    )
