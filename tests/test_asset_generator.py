import unittest

from opencode_proxy.asset_generator import get_web_asset_generator_context, is_asset_generation_prompt


class TestAssetGenerator(unittest.TestCase):

    def test_asset_generation_prompt(self):
        prompt = "Create a favicon suite and PWA Open Graph image for my coffee shop website"
        self.assertTrue(is_asset_generation_prompt(prompt))
        ctx = get_web_asset_generator_context(prompt)
        self.assertIn("WEB ASSET GENERATOR SKILL ACTIVE", ctx)
        self.assertIn("Favicon Suite", ctx)
        self.assertIn("Mobile App Icons", ctx)

    def test_non_asset_prompt(self):
        prompt = "Fix database query optimization"
        self.assertFalse(is_asset_generation_prompt(prompt))
        ctx = get_web_asset_generator_context(prompt)
        self.assertEqual(ctx, "")


if __name__ == "__main__":
    unittest.main()
