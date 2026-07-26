import pytest
from opencode_proxy.orchestrator import classify_intent, orchestrate_payload


def test_classify_intent():
    assert classify_intent({"messages": [{"role": "user", "content": "Refactor this function using TDD"}]}) == "refactor"
    assert classify_intent({"messages": [{"role": "user", "content": "Debug this memory leak crash"}]}) == "debugging"
    assert classify_intent({"messages": [{"role": "user", "content": "How to use upstash context7 documentation"}]}) == "docs"
    assert classify_intent({"messages": [{"role": "user", "content": "Audit code for security vulnerabilities"}]}) == "security"
    assert classify_intent({"messages": [{"role": "user", "content": "Write unit tests for pytest"}]}) == "qa"
    assert classify_intent({"messages": [{"role": "user", "content": "Hello world"}]}) == "general"


def test_orchestrate_payload():
    payload_refactor = {"messages": [{"role": "user", "content": "Refactor this module using TDD"}]}
    context = orchestrate_payload(payload_refactor)
    assert "PRINCIPAL SOFTWARE ARCHITECT" in context
    assert "OBRA/SUPERPOWERS" in context

    payload_debug = {"messages": [{"role": "user", "content": "Debug this crash"}]}
    context_debug = orchestrate_payload(payload_debug)
    assert "SEQUENTIAL THINKING MCP" in context_debug
