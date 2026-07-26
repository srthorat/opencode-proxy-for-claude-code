import pathlib
import pytest

from opencode_proxy.adr_generator import generate_adr_document, should_generate_adr
from opencode_proxy.api_diff_guard import check_api_breaking_changes, _extract_function_signatures
from opencode_proxy.debt_scanner import scan_python_file_for_debt
from opencode_proxy.pattern_memory import init_pattern_db, search_patterns, store_pattern
from opencode_proxy.solid_enforcer import enforce_solid_on_code, format_solid_report


# ── ADR Generator ─────────────────────────────────────────────────────────────

def test_adr_trigger_detection():
    assert should_generate_adr("migrate database to PostgreSQL") is True
    assert should_generate_adr("fix typo in README") is False


def test_adr_document_generation(tmp_path):
    adr_path = generate_adr_document(
        workspace_dir=tmp_path,
        title="Migrate Auth to JWT",
        context="Current session tokens are not stateless.",
        decision="Switch to JWT for stateless authentication.",
    )
    assert adr_path is not None
    assert adr_path.exists()
    content = adr_path.read_text()
    assert "Migrate Auth to JWT" in content
    assert "Switch to JWT" in content
    assert "Draft" in content


# ── Technical Debt Scanner ───────────────────────────────────────────────────

def test_debt_scanner_long_function(tmp_path):
    long_func = "def long_function():\n" + "    x = 1\n" * 60 + "    return x\n"
    pyfile = tmp_path / "sample.py"
    pyfile.write_text(long_func)
    issues = scan_python_file_for_debt(pyfile)
    long_issues = [i for i in issues if i.issue_type == "Long Function"]
    assert len(long_issues) >= 1


# ── Cross-Session Pattern Memory ─────────────────────────────────────────────

def test_pattern_memory_store_and_search(tmp_path):
    db = tmp_path / "patterns.db"
    store_pattern("Race condition in async auth middleware", db_file=db)
    store_pattern("JWT token expiry not handled on frontend", db_file=db)
    results = search_patterns("auth", db_file=db)
    assert len(results) >= 1
    assert any("auth" in r["description"].lower() for r in results)


# ── SOLID Principle Enforcer ─────────────────────────────────────────────────

def test_solid_enforcer_srp_violation():
    fat_class = "class BigClass:\n" + "\n".join(
        f"    def method_{i}(self): pass" for i in range(12)
    )
    violations = enforce_solid_on_code(fat_class)
    principles = [v.principle for v in violations]
    assert any("Single Responsibility" in p for p in principles)


def test_solid_enforcer_clean_code():
    clean_code = "class SmallClass:\n    def do_one_thing(self): pass\n"
    violations = enforce_solid_on_code(clean_code)
    srp_violations = [v for v in violations if "Single Responsibility" in v.principle]
    assert len(srp_violations) == 0


# ── API Contract Diff Guard ───────────────────────────────────────────────────

def test_api_diff_guard_signature_extraction():
    code = "def get_user(user_id: int) -> str: ...\ndef delete_user(user_id: int) -> None: ...\n"
    sigs = _extract_function_signatures(code)
    assert "get_user" in sigs
    assert "delete_user" in sigs


def test_api_diff_guard_non_git_dir(tmp_path):
    pyfile = tmp_path / "api.py"
    pyfile.write_text("def hello() -> str: return 'hi'\n")
    changes = check_api_breaking_changes(pyfile, workspace_dir=tmp_path)
    assert changes == []  # No git history → no baseline → no breaking changes
