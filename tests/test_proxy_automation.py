import pytest
from opencode_proxy.memory_db import (
    get_workspace_memory_summary,
    record_graph_node,
    record_observation,
)
from opencode_proxy.observer import observe_payload


def test_memory_db_operations(tmp_path):
    db_file = tmp_path / "test_memory.db"
    workspace = "/tmp/test-workspace"

    record_observation(
        workspace_path=workspace,
        content="Refactored router module to support key rotation",
        file_path="opencode_proxy/router.py",
        category="refactor",
        db_file=db_file,
    )

    record_graph_node(
        workspace_path=workspace,
        node_label="auto_select_model",
        node_type="function",
        file_path="opencode_proxy/router.py",
        db_file=db_file,
    )

    summary = get_workspace_memory_summary(workspace_path=workspace, db_file=db_file)
    assert "PROXY SERVER MEMORY & CODEBASE CONTEXT" in summary
    assert "[function] auto_select_model (opencode_proxy/router.py)" in summary
    assert "Refactored router module to support key rotation" in summary


def test_observer_payload_parsing(tmp_path, monkeypatch):
    db_file = tmp_path / "test_obs.db"
    monkeypatch.setattr("opencode_proxy.memory_db.DB_PATH", db_file)

    workspace = "/tmp/observed-workspace"
    payload = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "read_file",
                        "input": {"TargetFile": "opencode_proxy/main.py"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": "def test_server_function(): pass\nclass ServerManager: pass",
                    }
                ],
            },
        ]
    }

    observe_payload(payload, workspace_path=workspace)

    summary = get_workspace_memory_summary(workspace_path=workspace, db_file=db_file)
    assert "main.py" in summary
    assert "test_server_function" in summary
    assert "ServerManager" in summary
