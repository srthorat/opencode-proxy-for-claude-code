import unittest
from unittest.mock import AsyncMock, MagicMock

from opencode_proxy.distiller import semantic_prune_prompt, trim_system_prompt
from opencode_proxy.guards import self_heal_code_syntax, validate_code_syntax
from opencode_proxy.indexer import link_monorepo_context, search_monorepo_symbols
from opencode_proxy.racing import race_upstream_models


class TestUltimateSuperpowers(unittest.IsolatedAsyncioTestCase):

    def test_semantic_prune_prompt(self):
        chatter = "Sure, I'd be happy to help with that!\n\ndef hello():\n    return 'world'"
        pruned = semantic_prune_prompt(chatter)
        self.assertNotIn("Sure, I'd be happy to help", pruned)
        self.assertIn("def hello():", pruned)

    def test_self_heal_code_syntax(self):
        broken_json = '{"name": "opencode-proxy", "status": "ok"'
        valid, err = validate_code_syntax(broken_json, "test.json")
        self.assertFalse(valid)
        healed = self_heal_code_syntax(broken_json, err)
        valid_after, _ = validate_code_syntax(healed, "test.json")
        self.assertTrue(valid_after)

    def test_link_monorepo_context(self):
        ctx = link_monorepo_context("How does process_user_request work in orchestrator?")
        self.assertIsInstance(ctx, str)

    async def test_race_upstream_models(self):
        mock_client = MagicMock()
        mock_resp_a = MagicMock()
        mock_resp_a.status_code = 200

        mock_client.build_request.return_value = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_resp_a)

        req_a = {"url": "http://localhost:8080/v1", "headers": {}, "content": b"{}"}
        req_b = {"url": "http://localhost:8080/v2", "headers": {}, "content": b"{}"}

        winner = await race_upstream_models(mock_client, req_a, req_b, timeout_seconds=1.0)
        self.assertIsNotNone(winner)
        self.assertEqual(winner.status_code, 200)


if __name__ == "__main__":
    unittest.main()
