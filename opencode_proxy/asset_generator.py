"""
opencode-proxy asset_generator
────────────────────────────────
Web Asset Generator Skill: Generates favicons, PWA mobile icons, and Open Graph
social media images from logos, text, or emojis.
"""
import logging
import re

logger = logging.getLogger("opencode-proxy.asset_generator")

ASSET_PATTERNS = re.compile(
    r"\b(favicon|pwa|app icon|open graph|og image|social image|manifest\.json|apple-touch-icon)\b",
    re.I,
)


def is_asset_generation_prompt(user_text: str) -> bool:
    """Return True if prompt requires Web Asset Generator skill."""
    if not user_text or not isinstance(user_text, str):
        return False
    return bool(ASSET_PATTERNS.search(user_text))


def get_web_asset_generator_context(user_text: str) -> str:
    """Inject Web Asset Generator guidelines into prompt context."""
    if not is_asset_generation_prompt(user_text):
        return ""

    logger.info("Web Asset Generator Skill auto-activated.")
    return (
        "\n--- WEB ASSET GENERATOR SKILL ACTIVE ---\n"
        "- Favicon Suite: Produce 16x16, 32x32, 96x96 PNGs and multi-resolution favicon.ico.\n"
        "- Mobile App Icons: Generate 180x180 (apple-touch-icon), 192x192, and 512x512 PWA icons.\n"
        "- Social Media Open Graph: Create 1200x630 (og:image) and 1200x675 (twitter:image) banners.\n"
        "- PWA Manifest Integration: Auto-generate valid manifest.json with theme_color, background_color, and icon mappings.\n"
        "- Contrast & Accessibility: Ensure minimum WCAG 4.5:1 text-to-background contrast ratio.\n"
        "--- END WEB ASSET GENERATOR ---\n"
    )
