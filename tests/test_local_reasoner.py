import pytest
from unittest.mock import MagicMock, patch

from opencode_proxy.local_reasoner import predict_intent_with_smollm2
from opencode_proxy.orchestrator import classify_intent


def test_smollm2_local_reasoner_offline():
    # When local SmolLM2 endpoint is offline/unreachable, returns None cleanly
    res = predict_intent_with_smollm2("Refactor this module", timeout_seconds=0.01)
    assert res is None


def test_smollm2_local_reasoner_mock_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"response": "{\\"intent\\": \\"debugging\\"}"}'

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = predict_intent_with_smollm2("Fix memory leak crash in loop", timeout_seconds=0.1)
        assert res == "debugging"


def test_orchestrator_with_smollm2_fallback():
    # Verify orchestrator classifies intent via fallback heuristics when SmolLM2 offline
    intent = classify_intent({"messages": [{"role": "user", "content": "Refactor this code using TDD"}]})
    assert intent == "refactor"


def test_judge_best_response_with_smollm2():
    from opencode_proxy.local_reasoner import judge_best_response_with_smollm2

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"response": "{\\"winner\\": \\"B\\"}"}'

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        winner = judge_best_response_with_smollm2(
            "Write a function",
            text_a="def f(): pass",
            text_b="def f():\n    return 42",
            timeout_seconds=0.1,
        )
        assert winner == "B"

