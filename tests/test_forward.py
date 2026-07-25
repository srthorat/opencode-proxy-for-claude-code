"""Tests for forward.py — _build_target_url.

Exercises path rewriting, /v1 deduplication, and query-string stripping in
isolation by constructing a minimal RequestContext and asserting ctx.target_url.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context import RequestContext
from forward import _build_target_url, _forward_to_upstream

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_ctx(**overrides) -> RequestContext:
    """Return a minimal RequestContext suitable for _build_target_url tests."""
    defaults: dict[str, Any] = dict(
        method="POST",
        path="/v1/messages",
        query="",
        headers={},
        body=b"",
        content_type="application/json",
        per_request_upstream_url="https://api.example.com",
        need_protocol_conv=False,
        send_content=None,
    )
    defaults.update(overrides)
    return RequestContext(**defaults)


# ---------------------------------------------------------------------------
# TestBuildTargetUrl
# ---------------------------------------------------------------------------


class TestBuildTargetUrl:
    # ── /v1/messages ────────────────────────────────────────────────────────

    def test_messages_with_protocol_conv_becomes_chat_completions(self):
        ctx = make_ctx(path="/v1/messages", need_protocol_conv=True)
        _build_target_url(ctx)
        assert ctx.target_url == "https://api.example.com/chat/completions"

    def test_messages_without_protocol_conv_preserved(self):
        ctx = make_ctx(path="/v1/messages", need_protocol_conv=False)
        _build_target_url(ctx)
        assert ctx.target_url == "https://api.example.com/v1/messages"

    # ── /v1/completions → /chat/completions ────────────────────────────────

    def test_completions_path_remapped(self):
        ctx = make_ctx(path="/v1/completions")
        _build_target_url(ctx)
        assert ctx.target_url == "https://api.example.com/chat/completions"

    # ── /v1/chat/completions → /chat/completions ────────────────────────────

    def test_chat_completions_path_normalized(self):
        ctx = make_ctx(path="/v1/chat/completions")
        _build_target_url(ctx)
        assert ctx.target_url == "https://api.example.com/chat/completions"

    # ── Base URL with /v1 suffix — no double /v1/v1/ ─────────────────────────

    def test_base_with_v1_avoids_double_v1_on_chat_completions(self):
        ctx = make_ctx(
            path="/v1/chat/completions",
            per_request_upstream_url="https://api.example.com/v1",
        )
        _build_target_url(ctx)
        assert ctx.target_url == "https://api.example.com/v1/chat/completions"
        assert "/v1/v1/" not in ctx.target_url

    def test_base_with_v1_avoids_double_v1_on_protocol_conv(self):
        ctx = make_ctx(
            path="/v1/messages",
            need_protocol_conv=True,
            per_request_upstream_url="https://api.example.com/v1",
        )
        _build_target_url(ctx)
        assert ctx.target_url == "https://api.example.com/v1/chat/completions"
        assert "/v1/v1/" not in ctx.target_url

    def test_base_without_v1_suffix_keeps_path_v1(self):
        ctx = make_ctx(
            path="/v1/messages",
            need_protocol_conv=False,
            per_request_upstream_url="https://api.example.com",
        )
        _build_target_url(ctx)
        # No /v1 suffix on base: path is preserved as-is
        assert ctx.target_url == "https://api.example.com/v1/messages"

    # ── Query-string stripping ───────────────────────────────────────────────

    def test_beta_query_param_stripped(self):
        ctx = make_ctx(
            path="/v1/messages",
            query="beta=2024-01-01&foo=bar",
            need_protocol_conv=True,
        )
        _build_target_url(ctx)
        assert "beta=" not in ctx.target_url
        assert "foo=bar" in ctx.target_url

    def test_betas_query_param_stripped(self):
        ctx = make_ctx(
            path="/v1/messages",
            query="betas=interleaved-thinking",
            need_protocol_conv=True,
        )
        _build_target_url(ctx)
        assert "betas" not in ctx.target_url
        # With nothing left, no query string appended
        assert "?" not in ctx.target_url

    def test_non_stripped_params_preserved(self):
        ctx = make_ctx(
            path="/v1/chat/completions",
            query="stream=true&model=foo",
        )
        _build_target_url(ctx)
        assert "stream=true" in ctx.target_url
        assert "model=foo" in ctx.target_url

    def test_empty_query_no_question_mark(self):
        ctx = make_ctx(path="/v1/messages", query="", need_protocol_conv=True)
        _build_target_url(ctx)
        assert "?" not in ctx.target_url

    # ── Trailing-slash tolerance ─────────────────────────────────────────────

    def test_base_url_trailing_slash_stripped(self):
        ctx = make_ctx(
            path="/v1/messages",
            need_protocol_conv=True,
            per_request_upstream_url="https://api.example.com/",
        )
        _build_target_url(ctx)
        # Should NOT produce double slash or dangling slash
        assert "//chat" not in ctx.target_url
        assert ctx.target_url.endswith("/chat/completions")

    # ── Collapse /v1/v1/ artefacts ───────────────────────────────────────────

    def test_no_v1_v1_duplication_in_output(self):
        """A well-formed base + path should never produce /v1/v1/."""
        ctx = make_ctx(
            path="/v1/chat/completions",
            per_request_upstream_url="https://api.example.com/v1",
        )
        _build_target_url(ctx)
        assert "/v1/v1/" not in ctx.target_url


# ---------------------------------------------------------------------------
# TestFallbackRouting
# ---------------------------------------------------------------------------


class TestFallbackRouting:
    @pytest.mark.asyncio
    async def test_fallback_routing_uses_config_key(self):
        # Prepare a mock context with a model key that has fallbacks (e.g., big-pickle)
        ctx = make_ctx(
            method="POST",
            path="/v1/messages",
            resolved_model="big-pickle",
            config_model_key="big-pickle",
            per_request_upstream_url="https://api.opencode.ai/zen/v1",
            need_protocol_conv=True,
            is_auto_routed=True,
        )

        # We need mock responses: 429 for the first model, 200 for the fallback model (north-mini-code-free)
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"content-type": "application/json"}
        mock_resp_429.aread = AsyncMock(return_value=b'{"error": "rate limited"}')
        mock_resp_429.aclose = AsyncMock()

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.headers = {"content-type": "application/json"}
        mock_resp_200.aread = AsyncMock(return_value=b'{"choices": [{"message": {"content": "ok"}}]}')
        mock_resp_200.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request.return_value = MagicMock()
        # First send returns 429, second returns 200
        mock_client.send = AsyncMock(side_effect=[mock_resp_429, mock_resp_200])

        with patch("forward.get_client", AsyncMock(return_value=mock_client)):
            with patch("forward.resolve_model_config") as mock_resolve:
                # Mock resolve_model_config for north-mini-code-free fallback
                mock_resolve.side_effect = lambda m: (
                    ("north-mini-code-free", "https://api.opencode.ai/zen/v1", "mock-key", "free_coders/simple+classifier")
                    if m == "north-mini-code-free"
                    else (
                        "big-pickle",
                        "https://api.opencode.ai/zen/v1",
                        "mock-key",
                        "free_coders/trivial",
                    )
                )

                _build_target_url(ctx)
                resp = await _forward_to_upstream(ctx)

        # Assert that it successfully retried and got 200 from the fallback
        assert resp.status_code == 200
        # Assert that the client was called twice
        assert mock_client.send.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_routing_on_credits_error(self):
        # Prepare a mock context with a model key that has fallbacks (e.g., big-pickle)
        ctx = make_ctx(
            method="POST",
            path="/v1/messages",
            resolved_model="big-pickle",
            config_model_key="big-pickle",
            per_request_upstream_url="https://api.opencode.ai/zen/v1",
            need_protocol_conv=True,
            is_auto_routed=True,
        )

        # We need mock responses: 401 CreditsError for the first model, 200 for the fallback model (north-mini-code-free)
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        mock_resp_401.headers = {"content-type": "application/json"}
        mock_resp_401.aread = AsyncMock(return_value=b'{"type":"error","error":{"type":"CreditsError","message":"No payment method."}}')
        mock_resp_401.aclose = AsyncMock()

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.headers = {"content-type": "application/json"}
        mock_resp_200.aread = AsyncMock(return_value=b'{"choices": [{"message": {"content": "ok"}}]}')
        mock_resp_200.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request.return_value = MagicMock()
        mock_client.send = AsyncMock(side_effect=[mock_resp_401, mock_resp_200])

        with patch("forward.get_client", AsyncMock(return_value=mock_client)):
            with patch("forward.resolve_model_config") as mock_resolve:
                mock_resolve.side_effect = lambda m: (
                    ("north-mini-code-free", "https://api.opencode.ai/zen/v1", "mock-key", "free_coders/simple+classifier")
                    if m == "north-mini-code-free"
                    else (
                        "big-pickle",
                        "https://api.opencode.ai/zen/v1",
                        "mock-key",
                        "free_coders/trivial",
                    )
                )

                _build_target_url(ctx)
                resp = await _forward_to_upstream(ctx)

        assert resp.status_code == 200
        assert mock_client.send.call_count == 2
