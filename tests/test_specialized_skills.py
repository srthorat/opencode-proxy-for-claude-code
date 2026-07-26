import pathlib
import unittest

from opencode_proxy.api_contract import get_api_contract_context
from opencode_proxy.infra_terraform import get_infra_terraform_context
from opencode_proxy.obsidian_vault import get_obsidian_vault_summary, sync_adr_to_obsidian
from opencode_proxy.query_optimizer import get_query_optimization_context


class TestSpecializedSkills(unittest.TestCase):

    def test_query_optimizer_skill(self):
        sql = "SELECT id, name FROM users WHERE email = 'test@example.com' JOIN orders ON users.id = orders.user_id"
        ctx = get_query_optimization_context(sql)
        self.assertIn("DATABASE QUERY OPTIMIZER SKILL ACTIVE", ctx)
        self.assertIn("B-Tree indexes", ctx)

    def test_infra_terraform_skill(self):
        prompt = "Create a Terraform HCL script to deploy a Kubernetes ingress pod on AWS"
        ctx = get_infra_terraform_context(prompt)
        self.assertIn("CLOUD INFRASTRUCTURE & TERRAFORM SKILL ACTIVE", ctx)
        self.assertIn("Terraform Security", ctx)

    def test_api_contract_skill(self):
        prompt = "Define an OpenAPI 3.0 schema and Protobuf gRPC endpoint"
        ctx = get_api_contract_context(prompt)
        self.assertIn("MICROSERVICE API CONTRACT SKILL ACTIVE", ctx)
        self.assertIn("Backwards Compatibility", ctx)

    def test_obsidian_vault_sync(self, tmp_path=None):
        tmp_dir = pathlib.Path("/tmp/test_obsidian_vault")
        path = sync_adr_to_obsidian("Use PostgreSQL for Event Store", "We decided to use Postgres.", vault_dir=tmp_dir)
        self.assertTrue(path.endswith(".md"))
        summary = get_obsidian_vault_summary(vault_dir=tmp_dir)
        self.assertIn("OBSIDIAN KNOWLEDGE VAULT INTEGRATION", summary)
        self.assertIn("PostgreSQL", summary)


if __name__ == "__main__":
    unittest.main()
