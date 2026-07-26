import pathlib
import unittest

from opencode_proxy.flash_cache import get_flash_cache, set_flash_cache
from opencode_proxy.gemini_graph import index_file_symbols, init_gemini_graph_db, query_gemini_workspace_graph
from opencode_proxy.opus_reasoner import generate_opus_pass1_plan, is_opus_reasoning_required


class TestOpusGeminiPowers(unittest.TestCase):

    def test_opus_reasoner_pass1_plan(self):
        prompt = "Refactor database architecture and optimize security audit pipeline"
        self.assertTrue(is_opus_reasoning_required(prompt))
        plan = generate_opus_pass1_plan(prompt)
        self.assertIn("OPUS-STYLE MULTI-PASS REASONING PLAN", plan)
        self.assertIn("Risk Matrix", plan)

    def test_gemini_graph_sqlite(self):
        tmp_db = pathlib.Path("/tmp/test_gemini_graph.db")
        if tmp_db.exists():
            tmp_db.unlink()

        init_gemini_graph_db(tmp_db)
        count = index_file_symbols("opencode_proxy/local_reasoner.py", "opencode-proxy", db_file=tmp_db)
        self.assertGreater(count, 0)

        results = query_gemini_workspace_graph("predict_intent", db_file=tmp_db)
        self.assertGreaterEqual(len(results), 1)

    def test_flash_cache(self):
        key = "test_ast_signature_cache"
        val = {"ast": "FunctionDef(predict)"}
        set_flash_cache(key, val)
        cached = get_flash_cache(key)
        self.assertEqual(cached, val)


if __name__ == "__main__":
    unittest.main()
