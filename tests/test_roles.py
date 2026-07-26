import pytest
from opencode_proxy.personas import get_role_persona_summary
from opencode_proxy.skills_matcher import match_and_get_skills_context


def test_role_personas():
    cto_summary = get_role_persona_summary("role-cto")
    assert "PERSONA: CTO" in cto_summary
    assert "scalability" in cto_summary

    arch_summary = get_role_persona_summary("role-architect")
    assert "PERSONA: SOFTWARE ARCHITECT" in arch_summary

    qa_summary = get_role_persona_summary("role-qa-architect")
    assert "PERSONA: QA ARCHITECT" in qa_summary


def test_role_level_intent_matching():
    payload_cto = {
        "messages": [
            {"role": "user", "content": "As CTO, evaluate the long-term scalability and architecture of this codebase"}
        ]
    }
    ctx = match_and_get_skills_context(payload_cto)
    assert "PERSONA: CTO" in ctx

    payload_qa = {
        "messages": [
            {"role": "user", "content": "Act as QA Architect to design an automated test strategy"}
        ]
    }
    ctx_qa = match_and_get_skills_context(payload_qa)
    assert "PERSONA: QA ARCHITECT" in ctx_qa
