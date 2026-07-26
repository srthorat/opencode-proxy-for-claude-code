from fastapi.testclient import TestClient

from opencode_proxy.main import app


def test_admin_stats_includes_ccg_available():
    client = TestClient(app)
    response = client.get("/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert "integrations" in data
    assert "ccg_available" in data["integrations"]
    assert isinstance(data["integrations"]["ccg_available"], bool)
