import unittest

from opencode_proxy.ast_repair import auto_repair_missing_imports
from opencode_proxy.prefetcher import prefetch_related_file_skeletons
from opencode_proxy.stream_accelerator import accelerate_stream_chunk


class TestWorldClassPowers(unittest.TestCase):

    def test_auto_repair_missing_imports(self):
        broken_code = "def calculate():\n    return json.dumps({'status': 'ok'})\n"
        repaired, flag = auto_repair_missing_imports(broken_code)
        self.assertTrue(flag)
        self.assertIn("import json", repaired)

    def test_prefetcher_skeleton_scan(self):
        prefetched = prefetch_related_file_skeletons("opencode_proxy/forward.py")
        self.assertIsInstance(prefetched, list)

    def test_stream_accelerator(self):
        raw_bytes = b"event: message\r\ndata: {}\r\n\r\n"
        acc = accelerate_stream_chunk(raw_bytes)
        self.assertNotIn(b"\r\n", acc)
        self.assertIn(b"\n", acc)


if __name__ == "__main__":
    unittest.main()
