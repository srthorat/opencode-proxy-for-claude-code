"""Integration tests — boots the FastAPI app via TestClient and exercises the
full request pipeline with mocked upstream.

Covers:
  - Health check returns 200
  - count_tokens endpoint returns estimated token count
  - Auth rejection when PROXY_API_KEY is set
  - Request size limit returns 413
  - HEAD / returns 200
  - Proxy route (non-streaming JSON) with mocked upstream
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app — main.py registers all routes.
from main import app


# ---------------------------------------------------------------------------
# Shared test client helper
# ---------------------------------------------------------------------------

def get_client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthz:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/healthz")
        assert resp.status_code == 200

    def test_returns_json_with_status_ok(self):
        client = get_client()
        resp = client.get("/healthz")
        data = resp.json()
        assert data["status"] == "ok"
        assert "upstream" in data


# ---------------------------------------------------------------------------
# HEAD liveness probe
# ---------------------------------------------------------------------------

class TestHeadLiveness:
    def test_head_root_returns_200(self):
        client = get_client()
        resp = client.head("/")
        assert resp.status_code == 200

    def test_head_path_returns_200(self):
        client = get_client()
        resp = client.head("/v1/messages")
        assert resp.status_code == 200

    def test_head_arbitrary_path_returns_200(self):
        client = get_client()
        resp = client.head("/some/deep/path")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# count_tokens endpoint
# ---------------------------------------------------------------------------

class TestCountTokens:
    def test_returns_200(self):
        client = get_client()
        resp = client.post(
            "/v1/messages/count_tokens",
            json={"model": "test", "messages": [{"role": "user", "content": "Hello world"}]},
        )
        assert resp.status_code == 200

    def test_returns_input_tokens_field(self):
        client = get_client()
        resp = client.post(
            "/v1/messages/count_tokens",
            json={"model": "test", "messages": [{"role": "user", "content": "Hello world"}]},
        )
        assert "input_tokens" in resp.json()

    def test_token_count_is_positive(self):
        client = get_client()
        resp = client.post(
            "/v1/messages/count_tokens",
            json={"model": "test", "messages": [{"role": "user", "content": "Hello world"}]},
        )
        assert resp.json()["input_tokens"] > 0

    def test_empty_messages_returns_minimum_one(self):
        client = get_client()
        resp = client.post(
            "/v1/messages/count_tokens",
            json={"model": "test", "messages": []},
        )
        assert resp.json()["input_tokens"] >= 1

    def test_longer_content_gives_higher_count(self):
        client = get_client()
        short_resp = client.post(
            "/v1/messages/count_tokens",
            json={"model": "test", "messages": [{"role": "user", "content": "Hi"}]},
        )
        long_resp = client.post(
            "/v1/messages/count_tokens",
            json={"model": "test", "messages": [
                {"role": "user", "content": "a" * 1000}
            ]},
        )
        assert long_resp.json()["input_tokens"] > short_resp.json()["input_tokens"]

    def test_invalid_json_body_returns_zero(self):
        client = get_client()
        resp = client.post(
            "/v1/messages/count_tokens",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["input_tokens"] == 0


# ---------------------------------------------------------------------------
# Request size limit (50 MB cap)
# ---------------------------------------------------------------------------

class TestRequestSizeLimit:
    def test_large_content_length_returns_413(self):
        client = get_client()
        # Declare a body larger than 50 MB via Content-Length header
        resp = client.post(
            "/v1/messages",
            headers={"Content-Length": str(51 * 1024 * 1024)},
            content=b"x",  # actual body doesn't need to match for the header check
        )
        assert resp.status_code == 413

    def test_large_content_length_returns_error_json(self):
        client = get_client()
        resp = client.post(
            "/v1/messages",
            headers={"Content-Length": str(51 * 1024 * 1024)},
            content=b"x",
        )
        assert "error" in resp.json()

    def test_acceptable_content_length_passes_middleware(self):
        """A request within the size limit must not be rejected by middleware."""
        # Use count_tokens which needs no upstream — just verifies middleware passes it
        client = get_client()
        resp = client.post(
            "/v1/messages/count_tokens",
            json={"model": "test", "messages": []},
        )
        # Middleware should not have blocked this — any status other than 413 is fine
        assert resp.status_code != 413


# ---------------------------------------------------------------------------
# Auth rejection
# ---------------------------------------------------------------------------

class TestAuthRejection:
    def test_rejects_without_bearer_when_proxy_key_set(self):
        with patch("auth.PROXY_API_KEY", "test-secret"):
            client = get_client()
            resp = client.post(
                "/v1/messages",
                json={"model": "test", "messages": []},
            )
        assert resp.status_code == 401

    def test_rejection_returns_error_json(self):
        with patch("auth.PROXY_API_KEY", "test-secret"):
            client = get_client()
            resp = client.post(
                "/v1/messages",
                json={"model": "test", "messages": []},
            )
        assert resp.json().get("error") == "unauthorized"

    def test_rejects_wrong_key(self):
        with patch("auth.PROXY_API_KEY", "correct-secret"):
            client = get_client()
            resp = client.post(
                "/v1/messages",
                headers={"Authorization": "Bearer wrong-secret"},
                json={"model": "test", "messages": []},
            )
        assert resp.status_code == 401

    def test_passes_with_correct_key(self):
        """Correct bearer token must pass auth (even if upstream fails)."""
        with patch("auth.PROXY_API_KEY", "correct-secret"):
            # Mock the upstream to avoid real HTTP
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"content-type": "application/json"}
            mock_resp.aread = AsyncMock(
                return_value=json.dumps({
                    "choices": [
                        {"message": {"content": "hi", "tool_calls": None},
                         "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1},
                }).encode()
            )
            mock_resp.aclose = AsyncMock()

            mock_client = MagicMock()
            mock_client.build_request.return_value = MagicMock()
            mock_client.send = AsyncMock(return_value=mock_resp)

            with patch("forward.get_client", AsyncMock(return_value=mock_client)):
                client = get_client()
                resp = client.post(
                    "/v1/messages",
                    headers={"Authorization": "Bearer correct-secret"},
                    json={
                        "model": "minimax-m3",  # Anthropic-compat model → no protocol conv
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
        # Auth passed; the mock upstream returned 200 → proxy returns 200
        assert resp.status_code == 200

    def test_no_auth_required_when_proxy_key_not_set(self):
        """When PROXY_API_KEY is not configured, every request is allowed."""
        with patch("auth.PROXY_API_KEY", None):
            # Use count_tokens — no upstream needed
            client = get_client()
            resp = client.post(
                "/v1/messages/count_tokens",
                json={"model": "test", "messages": []},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Proxy route — basic smoke test with mocked upstream
# ---------------------------------------------------------------------------

class TestProxyRoute:
    def _make_mock_client(self, response_body: dict, status_code: int = 200):
        """Return a mock httpx-like client that returns a canned JSON response."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.aread = AsyncMock(return_value=json.dumps(response_body).encode())
        mock_resp.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request.return_value = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_resp)
        return mock_client

    def test_proxy_returns_200_for_valid_request(self):
        oai_response = {
            "choices": [
                {"message": {"content": "Hello!", "tool_calls": None}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        mock_client = self._make_mock_client(oai_response)

        with patch("forward.get_client", AsyncMock(return_value=mock_client)):
            client = get_client()
            resp = client.post(
                "/v1/messages",
                json={
                    "model": "kimi-k2.7",  # OpenAI-compat model → triggers protocol conv
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )
        assert resp.status_code == 200

    def test_proxy_converts_openai_response_to_anthropic(self):
        """Response from an OpenAI-compat model must be returned in Anthropic format."""
        oai_response = {
            "id": "chatcmpl-test",
            "choices": [
                {"message": {"content": "Hi there", "tool_calls": None}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
        mock_client = self._make_mock_client(oai_response)

        with patch("forward.get_client", AsyncMock(return_value=mock_client)):
            client = get_client()
            resp = client.post(
                "/v1/messages",
                json={
                    "model": "kimi-k2.7",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )
        data = resp.json()
        assert data.get("type") == "message"
        assert data.get("role") == "assistant"
        assert isinstance(data.get("content"), list)

    def test_upstream_502_returned_to_client(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.aread = AsyncMock(return_value=b'{"error":"server error"}')
        mock_resp.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request.return_value = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_resp)

        with patch("forward.get_client", AsyncMock(return_value=mock_client)):
            client = get_client()
            resp = client.post(
                "/v1/messages",
                json={
                    "model": "kimi-k2.7",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )
        assert resp.status_code == 500
