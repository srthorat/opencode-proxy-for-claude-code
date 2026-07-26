import unittest

from opencode_proxy.analytics import get_analytics_summary, record_token_savings
from opencode_proxy.auto_test_gen import extract_function_names, verify_generated_code
from opencode_proxy.prompt_tuner import tune_system_prompt_for_intent


class TestNextGenSuperpowers(unittest.TestCase):

    def test_analytics_recording(self):
        record_token_savings(3500)
        summary = get_analytics_summary()
        self.assertGreaterEqual(summary["chars_saved"], 3500)
        self.assertGreaterEqual(summary["approx_tokens_saved"], 1000)

    def test_auto_test_gen(self):
        sample_code = "def calculate_total(a, b):\n    return a + b\n"
        funcs = extract_function_names(sample_code)
        self.assertIn("calculate_total", funcs)

        ok, msg = verify_generated_code(sample_code)
        self.assertTrue(ok)
        self.assertIn("1 functions verified", msg)

    def test_prompt_tuner(self):
        prompt = "Base system prompt"
        tuned = tune_system_prompt_for_intent(prompt, "refactor")
        self.assertIn("Auto-Tuner Guideline", tuned)
        self.assertIn("modular decomposition", tuned)


if __name__ == "__main__":
    unittest.main()
