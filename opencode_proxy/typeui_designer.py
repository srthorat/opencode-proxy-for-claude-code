"""
opencode-proxy typeui_designer
───────────────────────────────
TypeUI Design System Skill: Injects structured design tokens, visual style guidelines,
color palettes, Glassmorphism/backdrop-filter CSS, and component guardrails into UI/UX prompts.
"""
import logging
import re

logger = logging.getLogger("opencode-proxy.typeui_designer")

TYPEUI_PATTERNS = re.compile(
    r"\b(typeui|ui|design system|component|button|card|modal|dashboard|glassmorphism|tailwind|landing page|layout|css|theme|palette)\b",
    re.I,
)


def is_typeui_prompt(user_text: str) -> bool:
    """Return True if prompt requires TypeUI Design System skill."""
    if not user_text or not isinstance(user_text, str):
        return False
    return bool(TYPEUI_PATTERNS.search(user_text))


def get_typeui_design_context(user_text: str) -> str:
    """Inject TypeUI Design System tokens and aesthetic guidelines into prompt context."""
    if not is_typeui_prompt(user_text):
        return ""

    logger.info("TypeUI Design System Skill auto-activated.")
    return (
        "\n--- TYPEUI DESIGN SYSTEM SKILL ACTIVE ---\n"
        "- Aesthetic Philosophy: Premium, vibrant, modern UI with curated color tokens (avoid generic raw RGB).\n"
        "- Visual Hierarchy: Inter/Outfit typography, explicit baseline grid spacing (4px/8px scale), subtle micro-animations.\n"
        "- Modern CSS Effects: Use Glassmorphism (backdrop-filter: blur(12px)), smooth gradient accents, and dark-mode defaults.\n"
        "- Component Integrity: Accessible interactive states (:hover, :focus-visible, :active, :disabled).\n"
        "- WCAG Compliance: Enforce minimum 4.5:1 text-to-background contrast ratio.\n"
        "- TypeUI MCP Server: Connected via https://mcp.typeui.sh/mcp for design system sync.\n"
        "--- END TYPEUI DESIGN SYSTEM ---\n"
    )
