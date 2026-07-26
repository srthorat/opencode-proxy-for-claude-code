import unittest

from opencode_proxy.ccr_archive import archive_large_content, fetch_archived_content
from opencode_proxy.headroom_compact import compact_json_tabular
from opencode_proxy.progressive_aging import age_and_summarize_turns


class TestTop3Engines(unittest.TestCase):

    def test_engine2_ccr_archiving(self):
        huge_log = "ERROR: Failed connection\n" * 2000  # ~50,000 chars
        result = archive_large_content(huge_log, threshold=30000)
        self.assertIn("CCR_ARCHIVED", result)
        self.assertIn("key=", result)

        # Verify content was stored in DB
        key_hash = result.split("key=")[1].split(" ")[0]
        retrieved = fetch_archived_content(key_hash)
        self.assertEqual(retrieved, huge_log)

    def test_engine4_headroom_tabular_compaction(self):
        json_array_str = '[{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]'
        compacted = compact_json_tabular(json_array_str)
        self.assertIn("[HEADROOM_TABULAR_JSON]", compacted)
        self.assertIn("keys: id,name", compacted)
        self.assertIn("1,alice", compacted)

    def test_engine9_progressive_aging(self):
        messages = [{"role": "user", "content": f"Turn {i} question"} for i in range(12)]
        aged_messages = age_and_summarize_turns(messages, threshold_turns=8)
        self.assertLess(len(aged_messages), 12)
        self.assertIn("PROGRESSIVE_AGED_HISTORY_SUMMARY", aged_messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
