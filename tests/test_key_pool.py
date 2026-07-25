from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from opencode_proxy.forward import _build_target_url, _forward_to_upstream
from opencode_proxy.key_pool import KeyPool
from tests.test_forward import make_ctx


class TestKeyPoolUnit:
    @pytest.mark.asyncio
    async def test_get_key_order_and_fallback(self):
        # Create pool with 3 mock keys
        keys = ["keyA", "keyB", "keyC"]
        kp = KeyPool(keys=keys, free_url="https://api.example.com")

        # Initially, all are healthy/unknown, so get_key returns first key
        assert kp.get_key("mimo-v2.5-free") == "keyA"

        # Demote keyA for mimo-v2.5-free
        kp.demote("keyA", "mimo-v2.5-free")
        assert kp.get_key("mimo-v2.5-free") == "keyB"

        # Demote keyB
        kp.demote("keyB", "mimo-v2.5-free")
        assert kp.get_key("mimo-v2.5-free") == "keyC"

        # Demote keyC
        kp.demote("keyC", "mimo-v2.5-free")
        assert kp.get_key("mimo-v2.5-free") is None

        # Promote keyB back
        kp.promote("keyB", "mimo-v2.5-free")
        assert kp.get_key("mimo-v2.5-free") == "keyB"

    @pytest.mark.asyncio
    async def test_health_snapshot(self):
        keys = ["keyA", "keyB"]
        kp = KeyPool(keys=keys, free_url="https://api.example.com")
        kp.demote("keyA", "mimo-v2.5-free")
        kp.promote("keyB", "mimo-v2.5-free")

        snap = kp.health_snapshot()
        assert snap["mimo-v2.5-free"]["key_1"] == "demoted"
        assert snap["mimo-v2.5-free"]["key_2"] == "healthy"
        # Others should be unknown
        assert snap["big-pickle"]["key_1"] == "unknown"

    @pytest.mark.asyncio
    async def test_probe_all(self):
        keys = ["keyA", "keyB"]
        kp = KeyPool(keys=keys, free_url="https://api.example.com")

        # We mock calls to post. For keyA all models succeed. For keyB we return 401.
        async def mock_post(url, **kwargs):
            headers = kwargs.get("headers", {})
            auth = headers.get("Authorization", "")
            json_data = kwargs.get("json", {})
            model = json_data.get("model")

            if "keyA" in auth:
                return httpx.Response(200, json={})
            elif "keyB" in auth:
                if model == "mimo-v2.5-free":
                    return httpx.Response(401, json={})
                else:
                    return httpx.Response(500, json={})  # 500 counts as demoted now!
            return httpx.Response(404, json={})

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            await kp.probe_all()

        # Check health states
        assert kp._health[("keyA", "mimo-v2.5-free")] is True
        assert kp._health[("keyB", "mimo-v2.5-free")] is False  # 401 demotes
        assert kp._health[("keyB", "big-pickle")] is False  # 500 demotes


class TestForwardKeyRotation:
    @pytest.mark.asyncio
    async def test_key_rotation_on_4xx_and_5xx(self):
        # Create a KeyPool with 3 keys
        keys = ["keyA", "keyB", "keyC"]
        kp = KeyPool(keys=keys, free_url="https://api.opencode.ai")

        ctx = make_ctx(
            method="POST",
            path="/v1/messages",
            resolved_model="mimo-v2.5-free",
            config_model_key="mimo-v2.5-free",
            per_request_upstream_url="https://api.opencode.ai/zen/v1",
            need_protocol_conv=True,
        )

        # 1st try: keyA -> returns 401
        # 2nd try: keyB -> returns 500
        # 3rd try: keyC -> returns 200
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        mock_resp_401.headers = {"content-type": "application/json"}
        mock_resp_401.aclose = AsyncMock()

        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_500.headers = {"content-type": "application/json"}
        mock_resp_500.aclose = AsyncMock()

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.headers = {"content-type": "application/json"}
        mock_resp_200.aread = AsyncMock(return_value=b'{"choices": [{"message": {"content": "ok"}}]}')
        mock_resp_200.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request.return_value = MagicMock()
        mock_client.send = AsyncMock(side_effect=[mock_resp_401, mock_resp_500, mock_resp_200])

        with patch("opencode_proxy.forward.get_client", AsyncMock(return_value=mock_client)):
            with patch("opencode_proxy.forward.pool", kp):
                _build_target_url(ctx)
                resp = await _forward_to_upstream(ctx)

        assert resp.status_code == 200
        assert mock_client.send.call_count == 3
        # Ensure keyA and keyB were demoted
        assert kp._health[("keyA", "mimo-v2.5-free")] is False
        assert kp._health[("keyB", "mimo-v2.5-free")] is False
        # And next selection returns keyC
        assert kp.get_key("mimo-v2.5-free") == "keyC"
