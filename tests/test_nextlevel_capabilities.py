import pytest

from opencode_proxy.guards import synthesize_consensus_response
from opencode_proxy.doctor import run_doctor_diagnostics
from opencode_proxy.git_guard import cleanup_isolated_worktree, create_isolated_worktree
from opencode_proxy.guards import scan_and_redact_secrets


def test_git_guard_non_git_repo(tmp_path):
    ok, path = create_isolated_worktree(tmp_path, branch_name="test-branch")
    assert ok is False
    assert path == str(tmp_path)


def test_security_guard_redaction():
    raw_code = 'AWS_KEY = "AKIA1234567890123456"\nOPENAI_KEY = "sk-12345678901234567890123456789012"'
    redacted, detected = scan_and_redact_secrets(raw_code)
    assert detected is True
    assert "AKIA1234567890123456" not in redacted
    assert "[REDACTED_AWS_ACCESS_KEY]" in redacted
    assert "[REDACTED_OPENAI_API_KEY]" in redacted


def test_consensus_engine():
    resp_a = "Solution A: Use Fast API"
    resp_b = "Solution B: Use Flask API"
    consensus = synthesize_consensus_response(resp_a, resp_b)
    assert "Solution A" in consensus
    assert "Solution B" in consensus
    assert "DUAL-MODEL CONSENSUS VERIFICATION" in consensus


def test_doctor_diagnostics():
    diag = run_doctor_diagnostics()
    assert isinstance(diag, dict)
    assert "skills_count" in diag
    assert "smollm2_reasoner_configured" in diag
