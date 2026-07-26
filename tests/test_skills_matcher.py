import pytest
from opencode_proxy.skills_matcher import match_and_get_skills_context


def test_skills_matcher_intent():
    payload_security = {
        "messages": [
            {"role": "user", "content": "Please review this authentication endpoint for security vulnerabilities and jwt secrets"}
        ]
    }

    context = match_and_get_skills_context(payload_security)
    assert "AUTOMATED MATCHED SKILLS & ROLE PERSONAS CONTEXT" in context
    assert "security-review" in context


def test_skills_matcher_expanded_keywords():
    payload_devops = {
        "messages": [
            {"role": "user", "content": "Help me optimize this docker container deployment for database migrations"}
        ]
    }

    context = match_and_get_skills_context(payload_devops)
    assert "AUTOMATED MATCHED SKILLS & ROLE PERSONAS CONTEXT" in context
    assert "devops-infra" in context
    assert "database-schema" in context


def test_skills_matcher_no_match():
    payload_generic = {
        "messages": [
            {"role": "user", "content": "Hello there how are you"}
        ]
    }

    context = match_and_get_skills_context(payload_generic)
    assert context == ""
