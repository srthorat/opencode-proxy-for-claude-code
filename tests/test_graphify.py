import json
import pytest
from opencode_proxy.graphify import load_graphify_summary


def test_graphify_missing_file(tmp_path):
    non_existent = tmp_path / "non_existent.json"
    result = load_graphify_summary(str(non_existent))
    assert result == ""


def test_graphify_invalid_json(tmp_path):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("not json content {", encoding="utf-8")
    result = load_graphify_summary(str(invalid_file))
    assert result == ""


def test_graphify_valid_graph(tmp_path):
    graph_file = tmp_path / "graph.json"
    sample_data = {
        "summary": "Sample test project for graphify testing.",
        "nodes": [
            {"id": "node1", "label": "main", "type": "function", "file": "main.py"},
            {"id": "node2", "label": "router", "type": "module", "file": "router.py"},
        ],
        "edges": [
            {"source": "main", "target": "router", "relation": "imports"},
        ],
    }
    graph_file.write_text(json.dumps(sample_data), encoding="utf-8")

    result = load_graphify_summary(str(graph_file))
    assert "GRAPHIFY KNOWLEDGE GRAPH CONTEXT" in result
    assert "Sample test project for graphify testing." in result
    assert "- [function] main (main.py)" in result
    assert "- main --[imports]--> router" in result
