import pytest
from fastapi.testclient import TestClient

from opencode_proxy.main import app
from opencode_proxy.indexer import search_monorepo_symbols
from opencode_proxy.response_cache import get_cached_response, store_cached_response
from opencode_proxy.skeletonizer import skeletonize_code
from opencode_proxy.guards import validate_code_syntax


def test_skeletonizer():
    py_code = (
        "def compute_sum(a: int, b: int) -> int:\n"
        '    """Compute sum of two numbers."""\n'
        "    result = a + b\n"
        "    return result\n"
    )
    skeleton = skeletonize_code(py_code, filename="test.py")
    assert "def compute_sum(a: int, b: int) -> int:" in skeleton
    assert "Compute sum of two numbers." in skeleton
    assert "result = a + b" not in skeleton  # Body replaced with ...


def test_syntax_checker():
    valid_py = "def hello(): pass\n"
    ok, err = validate_code_syntax(valid_py, filename="test.py")
    assert ok is True
    assert err is None

    invalid_py = "def hello(: pass\n"
    ok_bad, err_bad = validate_code_syntax(invalid_py, filename="test.py")
    assert ok_bad is False
    assert "Syntax Error" in err_bad


def test_response_cache(tmp_path):
    mock_db = tmp_path / "cache.db"
    payload = {"model": "mimo-v2.5-free", "messages": [{"role": "user", "content": "Test cache query"}]}
    resp_data = {"id": "chatcmpl-123", "choices": [{"message": {"content": "Cached response"}}]}

    assert get_cached_response(payload, db_file=mock_db) is None
    store_cached_response(payload, model="mimo-v2.5-free", response_data=resp_data, db_file=mock_db)
    cached = get_cached_response(payload, db_file=mock_db)
    assert cached is not None
    assert cached["id"] == "chatcmpl-123"


def test_monorepo_linker(tmp_path):
    mock_graphs = tmp_path / "graphs"
    mock_graphs.mkdir()
    graph_file = mock_graphs / "repo1.json"
    graph_file.write_text(
        '{"summary": "Repo 1", "nodes": [{"label": "AuthService", "type": "class", "file": "auth.py"}]}',
        encoding="utf-8",
    )

    results = search_monorepo_symbols("AuthService", graphs_dir=mock_graphs)
    assert len(results) == 1
    assert results[0]["symbol"] == "AuthService"


def test_admin_dashboard_endpoint():
    client = TestClient(app)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert "opencode-proxy Super-Power Dashboard" in resp.text
