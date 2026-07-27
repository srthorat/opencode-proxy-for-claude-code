import unittest

from opencode_proxy.typeui_designer import get_typeui_design_context, is_typeui_prompt


class TestTypeUIDesigner(unittest.TestCase):

    def test_typeui_prompt_detection(self):
        prompt = "Create a TypeUI button component with Glassmorphism and Tailwind CSS styling"
        self.assertTrue(is_typeui_prompt(prompt))
        ctx = get_typeui_design_context(prompt)
        self.assertIn("TYPEUI DESIGN SYSTEM SKILL ACTIVE", ctx)
        self.assertIn("Glassmorphism", ctx)
        self.assertIn("WCAG Compliance", ctx)

    def test_non_typeui_prompt(self):
        prompt = "Write a SQL query to get user counts"
        self.assertFalse(is_typeui_prompt(prompt))
        ctx = get_typeui_design_context(prompt)
        self.assertEqual(ctx, "")


if __name__ == "__main__":
    unittest.main()
