import unittest

from opencode_proxy.deduplicator import deduplicate_messages
from opencode_proxy.loopback import autonomous_loopback_repair
from opencode_proxy.smart_balancer import get_fastest_provider, get_provider_latency_summary, record_provider_latency


class TestMarketBeatingPowers(unittest.TestCase):

    def test_loopback_repair(self):
        broken_syntax = "def calculate_total(a, b)\n    return a + b\n"
        repaired, flag = autonomous_loopback_repair(broken_syntax, "SyntaxError")
        self.assertTrue(flag)
        self.assertTrue(repaired.strip().startswith("def calculate_total(a, b):"))

    def test_deduplicator(self):
        duplicate_text = "A" * 150
        messages = [
            {"role": "user", "content": duplicate_text},
            {"role": "user", "content": duplicate_text},
        ]
        removed_count = deduplicate_messages(messages)
        self.assertEqual(removed_count, 1)
        self.assertIn("Duplicate context snippet omitted", messages[1]["content"])

    def test_smart_balancer(self):
        record_provider_latency("ollama_local", 0.020)
        fastest = get_fastest_provider()
        self.assertEqual(fastest, "ollama_local")
        summary = get_provider_latency_summary()
        self.assertIn("ollama_local", summary)


if __name__ == "__main__":
    unittest.main()
