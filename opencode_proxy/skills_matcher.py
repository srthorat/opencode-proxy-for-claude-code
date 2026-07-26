import logging
import os
import pathlib
import re
from typing import Any

from .personas import get_role_persona_summary
from .skills_registry import get_discovered_skills


logger = logging.getLogger("opencode-proxy.skills_matcher")

# Expanded keyword-to-skill and engineering role level mapping triggers
KEYWORD_TRIGGERS = {
    # Engineering Role Levels & Personas
    "cto": "role-cto",
    "chief technology officer": "role-cto",
    "architect": "role-architect",
    "software architect": "role-architect",
    "solution architect": "role-architect",
    "principal": "role-principal",
    "principal engineer": "role-principal",
    "staff": "role-staff",
    "staff engineer": "role-staff",
    "senior": "role-senior",
    "senior engineer": "role-senior",
    "qa architect": "role-qa-architect",
    "test architect": "role-qa-architect",
    # Security & Audit
    "security": "security-review",
    "secret": "security-review",
    "vulnerability": "security-review",
    "cve": "security-review",
    "auth": "security-review",
    "jwt": "security-review",
    "password": "security-review",
    "token": "security-review",
    "leak": "security-review",
    "xss": "security-review",
    "csrf": "security-review",
    "encryption": "security-review",
    # Engineering & Architecture
    "review": "eng-review",
    "architecture": "eng-review",
    "refactor": "eng-review",
    "clean code": "eng-review",
    "optimize": "eng-review",
    "performance": "eng-review",
    "audit": "eng-review",
    "design": "eng-review",
    # Product Strategy & Planning
    "plan": "plan-ceo-review",
    "roadmap": "plan-ceo-review",
    "product": "plan-ceo-review",
    "strategy": "plan-ceo-review",
    "ceo": "plan-ceo-review",
    "feature": "plan-ceo-review",
    "spec": "plan-ceo-review",
    "prd": "plan-ceo-review",
    # QA & Unit Testing
    "test": "qa-review",
    "qa": "qa-review",
    "unittest": "qa-review",
    "pytest": "qa-review",
    "jest": "qa-review",
    "coverage": "qa-review",
    "mock": "qa-review",
    "assert": "qa-review",
    # Documents & PDF Extraction
    "pdf": "pdf-reader",
    "document": "pdf-reader",
    "invoice": "pdf-reader",
    "extract": "pdf-reader",
    # UI/UX Design Intelligence
    "ui": "ui-ux-pro-max",
    "ux": "ui-ux-pro-max",
    "design": "ui-ux-pro-max",
    "css": "ui-ux-pro-max",
    "frontend": "ui-ux-pro-max",
    "style": "ui-ux-pro-max",
    "theme": "ui-ux-pro-max",
    "color": "ui-ux-pro-max",
    "bento": "ui-ux-pro-max",
    "glassmorphism": "ui-ux-pro-max",
    "tailwind": "ui-ux-pro-max",
    "shadcn": "ui-ux-pro-max",
    # Web & E2E Automation
    "web": "web-tester",
    "browse": "web-tester",
    "browser": "web-tester",
    "playwright": "web-tester",
    "selenium": "web-tester",
    "dom": "web-tester",
    "e2e": "web-tester",

    # Database & SQL Schema
    "database": "database-schema",
    "db": "database-schema",
    "sql": "database-schema",
    "schema": "database-schema",
    "migration": "database-schema",
    "postgres": "database-schema",
    "sqlite": "database-schema",
    # API Design & REST
    "api": "api-design",
    "endpoint": "api-design",
    "rest": "api-design",
    "graphql": "api-design",
    "openapi": "api-design",
    # DevOps & Containers
    "docker": "devops-infra",
    "container": "devops-infra",
    "deploy": "devops-infra",
    "ci": "devops-infra",
    "cd": "devops-infra",
    "kubernetes": "devops-infra",
}


def load_skill_file_content(skill_name: str) -> str | None:
    """Check ~/.claude/skills/<skill_name>/SKILL.md or claude.md and return procedural instructions."""
    skills_dir = pathlib.Path.home() / ".claude" / "skills"
    if not skills_dir.exists():
        return None

    # Look for exact or subdirectory match
    for root, _, files in os.walk(skills_dir):
        folder_name = os.path.basename(root)
        if folder_name.lower() == skill_name.lower():
            for fname in files:
                if fname.lower() in ("skill.md", "skills.md", "claude.md"):
                    fpath = pathlib.Path(root) / fname
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore").strip()
                        # Extract first 1200 chars for token efficiency
                        if len(content) > 1200:
                            content = content[:1200] + "\n... [Skill instructions truncated for token budget]"
                        return content
                    except Exception:
                        pass
    return None


def format_skills_and_roles_context(skill_names: list[str]) -> str:
    """Format a list of skill/role names into structured system prompt context."""
    if not skill_names:
        return ""

    lines = ["\n--- AUTOMATED MATCHED SKILLS & ROLE PERSONAS CONTEXT ---"]
    for skill_name in skill_names:
        if skill_name.startswith("role-"):
            persona_text = get_role_persona_summary(skill_name)
            if persona_text:
                lines.append(persona_text.strip())
        else:
            lines.append(f"Auto-Activated Skill: [{skill_name}]")
            file_instructions = load_skill_file_content(skill_name)
            if file_instructions:
                lines.append(f"Procedural Instructions:\n{file_instructions}")
            else:
                lines.append(f"- Applied procedural rules and quality constraints for '{skill_name}'.")

    lines.append("--- END MATCHED CONTEXT ---\n")
    return "\n".join(lines)


def match_and_get_skills_context(payload: dict[str, Any]) -> str:
    """Analyze incoming prompt payload for keywords/intent and automatically load matching skill instructions and role level personas.

    Works 100% server-side even if the user never typed a slash command or skill tag.
    """
    if not isinstance(payload, dict):
        return ""

    messages = payload.get("messages", [])
    if not messages:
        return ""

    # Extract text from latest user message
    user_text = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_text += " " + content.lower()
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        user_text += " " + block.get("text", "").lower()
            break

    if not user_text.strip():
        return ""

    matched_skills: list[str] = []
    for keyword, skill_name in KEYWORD_TRIGGERS.items():
        if re.search(r"\b" + re.escape(keyword) + r"\b", user_text):
            if skill_name not in matched_skills:
                matched_skills.append(skill_name)

    if not matched_skills:
        return ""

    formatted = format_skills_and_roles_context(matched_skills)
    logger.info("Auto-activated skills/personas based on user prompt intent: %s", matched_skills)
    return formatted

