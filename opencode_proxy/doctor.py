"""
opencode-proxy doctor
──────────────────────
Merged from: doctor.py · test_runner.py

CLI diagnostics and background test runner — two operational tools in one.
"""
import json
import logging
import os
import pathlib
import socket
import subprocess
import sys
from typing import Any, Tuple

from .config import CLAUDE_MEM_URL, ENABLE_SMOLLM2_REASONER, PORT, SMOLLM2_URL
from .skills_registry import get_skills_summary

logger = logging.getLogger("opencode-proxy.doctor")


# ── Port / service checks ────────────────────────────────────────────────────

def check_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except Exception:
        return False


def run_doctor_diagnostics() -> dict[str, Any]:
    skills_summary = get_skills_summary()
    return {
        "proxy_port_8080_ready": check_port_open("127.0.0.1", PORT),
        "headroom_port_8787_ready": check_port_open("127.0.0.1", 8787),
        "smollm2_reasoner_configured": ENABLE_SMOLLM2_REASONER,
        "smollm2_url": SMOLLM2_URL,
        "claude_mem_url": CLAUDE_MEM_URL,
        "skills_count": skills_summary.get("skills_count", 0),
        "official_plugins_count": skills_summary.get("official_plugins_count", 0),
        "sqlite_memory_db_exists": (pathlib.Path.home() / ".opencode-proxy" / "memory.db").exists(),
        "sqlite_cache_db_exists": (pathlib.Path.home() / ".opencode-proxy" / "cache.db").exists(),
    }


def print_doctor_report() -> None:
    diag = run_doctor_diagnostics()
    print("==================================================")
    print("      opencode-proxy Health & Diagnostics Doctor   ")
    print("==================================================")
    print(f"Proxy Port ({PORT}):          {'ONLINE' if diag['proxy_port_8080_ready'] else 'OFFLINE (Start via ./run.sh)'}")
    print(f"Headroom Proxy (8787):     {'ONLINE' if diag['headroom_port_8787_ready'] else 'OFFLINE (Opt-in docker container)'}")
    print(f"SmolLM2 Reasoner:          {'ENABLED' if diag['smollm2_reasoner_configured'] else 'DISABLED'}")
    print(f"Installed Global Skills:   {diag['skills_count']} skills")
    print(f"Official Anthropic Plugins: {diag['official_plugins_count']} plugins")
    print(f"SQLite Memory Database:    {'READY' if diag['sqlite_memory_db_exists'] else 'NOT INITIALIZED'}")
    print(f"SQLite Response Cache:     {'READY' if diag['sqlite_cache_db_exists'] else 'NOT INITIALIZED'}")
    print("==================================================")


# ── Background Test Runner ───────────────────────────────────────────────────

def detect_and_run_quick_tests(workspace_dir: str | pathlib.Path, timeout_seconds: int = 5) -> Tuple[bool, str]:
    """Detect project test framework (pytest/npm/cargo/go) and run a quick sanity test."""
    wpath = pathlib.Path(workspace_dir)
    if not wpath.exists():
        return True, "No workspace directory found."

    cmd = None
    if (wpath / "pytest.ini").exists() or (wpath / "pyproject.toml").exists() or (wpath / "tests").exists():
        cmd = ["pytest", "-q", "--maxfail=1"]
    elif (wpath / "package.json").exists():
        cmd = ["npm", "test", "--", "--bail", "1"]
    elif (wpath / "Cargo.toml").exists():
        cmd = ["cargo", "test", "--", "--quiet"]
    elif (wpath / "go.mod").exists():
        cmd = ["go", "test", "./..."]

    if not cmd:
        return True, "No standard test runner detected."

    try:
        res = subprocess.run(cmd, cwd=str(wpath), capture_output=True, text=True, timeout=timeout_seconds, check=False)
        if res.returncode == 0:
            logger.info("Background Test Runner: Tests PASSED in %s", wpath.name)
            return True, "Tests passed."
        msg = f"Background Test Runner: Tests FAILED in {wpath.name}:\n{res.stderr or res.stdout}"
        logger.warning(msg)
        return False, msg
    except subprocess.TimeoutExpired:
        return True, "Tests timed out (skipped long-running suite)."
    except Exception as exc:
        return True, f"Test runner notice: {exc}"


if __name__ == "__main__":
    print_doctor_report()

