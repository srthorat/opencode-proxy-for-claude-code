import json
import time
import pytest
from opencode_proxy.graphify import get_global_graph_path, load_graphify_summary
from opencode_proxy.indexer import ensure_workspace_indexed


def test_auto_indexer_background(tmp_path, monkeypatch):
    mock_global_dir = tmp_path / "global_graphs"
    mock_global_dir.mkdir(parents=True)
    monkeypatch.setattr("opencode_proxy.graphify.GLOBAL_CACHE_DIR", mock_global_dir)

    # Create dummy project files
    project_dir = tmp_path / "sample_project"
    project_dir.mkdir()

    py_file = project_dir / "app.py"
    py_file.write_text(
        "def main_handler():\n    pass\n\nclass AppController:\n    pass\n",
        encoding="utf-8",
    )

    rs_file = project_dir / "lib.rs"
    rs_file.write_text(
        "pub fn process_data() {}\npub struct DataStore;\n",
        encoding="utf-8",
    )

    # Trigger background auto-indexer
    ensure_workspace_indexed(str(project_dir))

    # Wait briefly for background thread to complete
    time.sleep(0.5)

    global_path = get_global_graph_path(str(project_dir))
    assert global_path.exists()

    data = json.loads(global_path.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert len(data["nodes"]) > 0

    summary = load_graphify_summary(workspace_path=str(project_dir))
    assert "Auto-indexed codebase graph for sample_project" in summary
    assert "main_handler" in summary
    assert "AppController" in summary
