from fastapi.testclient import TestClient

from opencode_proxy.config import CLAUDE_MEM_URL
from opencode_proxy.main import app


def test_claude_mem_config():
    assert isinstance(CLAUDE_MEM_URL, str)
    assert CLAUDE_MEM_URL.startswith("http")


def test_admin_stats_includes_integrations():
    client = TestClient(app)
    response = client.get("/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert "integrations" in data
    assert "claude_mem_url" in data["integrations"]
    assert "graphify_context_enabled" in data["integrations"]
