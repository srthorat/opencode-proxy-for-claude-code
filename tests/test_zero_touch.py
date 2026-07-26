import json
import pytest
from opencode_proxy.graphify import (
    GLOBAL_CACHE_DIR,
    get_global_graph_path,
    get_workspace_hash,
    load_graphify_summary,
)


def test_workspace_hash():
    h1 = get_workspace_hash("/tmp/project1")
    h2 = get_workspace_hash("/tmp/project2")
    assert isinstance(h1, str)
    assert len(h1) == 32  # md5 hex length
    assert h1 != h2


def test_global_graph_fallback(tmp_path, monkeypatch):
    mock_global_dir = tmp_path / "global_graphs"
    mock_global_dir.mkdir(parents=True)
    monkeypatch.setattr("opencode_proxy.graphify.GLOBAL_CACHE_DIR", mock_global_dir)

    target_repo = "/tmp/my-external-zero-touch-repo"
    repo_hash = get_workspace_hash(target_repo)
    global_file = mock_global_dir / f"{repo_hash}.json"

    sample_graph = {
        "summary": "Global zero-touch architectural graph.",
        "nodes": [{"id": "n1", "label": "GlobalNode", "type": "class"}],
        "edges": [],
    }
    global_file.write_text(json.dumps(sample_graph), encoding="utf-8")

    # Verify that load_graphify_summary locates the graph from global cache via workspace_path
    summary = load_graphify_summary(workspace_path=target_repo)
    assert "Global zero-touch architectural graph." in summary
    assert "- [class] GlobalNode" in summary
