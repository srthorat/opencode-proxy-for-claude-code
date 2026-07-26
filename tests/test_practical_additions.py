import pytest

from opencode_proxy.router import get_fallback_model
from opencode_proxy.doctor import detect_and_run_quick_tests


def test_fallback_model_selection():
    fb1 = get_fallback_model("mimo-v2.5-free")
    assert fb1 == "north-mini-code-free"

    fb2 = get_fallback_model("unknown-custom-model")
    assert fb2 == "free-auto"


def test_test_runner_detection(tmp_path):
    # Empty directory returns True with notice
    ok, msg = detect_and_run_quick_tests(tmp_path)
    assert ok is True
    assert "No standard test runner detected" in msg
