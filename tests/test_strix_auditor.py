import unittest

from opencode_proxy.strix_auditor import get_strix_security_audit_context, is_security_audit_prompt


class TestStrixAuditor(unittest.TestCase):

    def test_strix_security_audit_prompt(self):
        prompt = "Audit this JWT auth handler for SQL injection and SSRF security vulnerabilities"
        self.assertTrue(is_security_audit_prompt(prompt))
        ctx = get_strix_security_audit_context(prompt)
        self.assertIn("STRIX DEFENSIVE SECURITY AUDITOR SKILL ACTIVE", ctx)
        self.assertIn("OWASP Top 10 Defenses", ctx)
        self.assertIn("SSRF & Network Hardening", ctx)

    def test_strix_non_security_prompt(self):
        prompt = "Write a function to format a timestamp"
        self.assertFalse(is_security_audit_prompt(prompt))
        ctx = get_strix_security_audit_context(prompt)
        self.assertEqual(ctx, "")


if __name__ == "__main__":
    unittest.main()
