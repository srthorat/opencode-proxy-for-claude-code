"""
opencode-proxy infra_terraform
───────────────────────────────
Cloud Infra & Terraform Skill: Validates Terraform HCL, Kubernetes manifests,
and Docker infrastructure configurations.
"""
import logging
import re

logger = logging.getLogger("opencode-proxy.infra_terraform")

IAC_PATTERNS = re.compile(r"\b(terraform|hcl|dockerfile|kubernetes|k8s|helm|ingress|pod|deployment|aws|gcp)\b", re.I)


def is_iac_prompt(user_text: str) -> bool:
    """Return True if prompt contains IaC or Cloud Infrastructure keywords."""
    if not user_text or not isinstance(user_text, str):
        return False
    return bool(IAC_PATTERNS.search(user_text))


def get_infra_terraform_context(user_text: str) -> str:
    """Inject Cloud Infra & Terraform guidelines into prompt context."""
    if not is_iac_prompt(user_text):
        return ""

    logger.info("Cloud Infra & Terraform Skill auto-activated.")
    return (
        "\n--- CLOUD INFRASTRUCTURE & TERRAFORM SKILL ACTIVE ---\n"
        "- Terraform Security: Require remote state locking (S3 + DynamoDB) and encrypted secrets.\n"
        "- Kubernetes Hardening: Specify non-root user execution, read-only root filesystems, and resource limits.\n"
        "- Container Optimization: Use multi-stage Docker builds to produce minimal 0-vulnerability image layers.\n"
        "--- END CLOUD INFRA SKILL ---\n"
    )
