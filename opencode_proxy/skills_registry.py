import json
import logging
import os
import pathlib
import re
from typing import Any

logger = logging.getLogger("opencode-proxy.skills_registry")

SKILLS_DIR = pathlib.Path.home() / ".claude" / "skills"
PLUGINS_DIR = pathlib.Path.home() / ".claude" / "plugins"

FRONTMATTER_NAME_REGEX = re.compile(r"^name:\s*[\"']?([^\"'\n]+)[\"']?", re.MULTILINE | re.IGNORECASE)


def get_discovered_skills(skills_path: pathlib.Path | None = None) -> list[dict[str, str]]:
    """Scan skills directory (~/.claude/skills/) and discover active SKILL.md packages."""
    target_dir = skills_path or SKILLS_DIR
    if not target_dir.exists():
        return []

    discovered: list[dict[str, str]] = []

    try:
        for root, _, files in os.walk(target_dir):
            for fname in files:
                if fname.lower() in ("skill.md", "skills.md", "claude.md"):
                    full_path = pathlib.Path(root) / fname
                    rel_dir = os.path.relpath(root, target_dir)
                    skill_name = os.path.basename(root)

                    try:
                        content = full_path.read_text(encoding="utf-8", errors="ignore")
                        match = FRONTMATTER_NAME_REGEX.search(content)
                        if match:
                            skill_name = match.group(1).strip()
                    except Exception:
                        pass

                    discovered.append(
                        {
                            "name": skill_name,
                            "path": rel_dir,
                            "file": fname,
                        }
                    )
    except Exception as exc:
        logger.warning("Failed to discover skills from %s: %s", target_dir, exc)

    return discovered


def get_discovered_plugins(plugins_path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Scan plugins directory (~/.claude/plugins/) and discover plugin.json manifests."""
    target_dir = plugins_path or PLUGINS_DIR
    if not target_dir.exists():
        return []

    discovered_plugins: list[dict[str, Any]] = []

    try:
        for root, _, files in os.walk(target_dir):
            for fname in files:
                if fname.lower() == "plugin.json":
                    full_path = pathlib.Path(root) / fname
                    try:
                        data = json.loads(full_path.read_text(encoding="utf-8", errors="ignore"))
                        plugin_name = data.get("name") or os.path.basename(os.path.dirname(root))
                        version = data.get("version", "1.0.0")
                        description = data.get("description", "")
                        discovered_plugins.append(
                            {
                                "name": plugin_name,
                                "version": version,
                                "description": description,
                                "path": os.path.relpath(root, target_dir),
                            }
                        )
                    except Exception as json_exc:
                        logger.warning("Failed to parse plugin.json at %s: %s", full_path, json_exc)
    except Exception as exc:
        logger.warning("Failed to discover plugins from %s: %s", target_dir, exc)

    return discovered_plugins


def get_skills_summary(
    skills_path: pathlib.Path | None = None,
    plugins_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Return summary dictionary of global skills and official plugins availability."""
    skills = get_discovered_skills(skills_path)
    plugins = get_discovered_plugins(plugins_path)
    return {
        "skills_count": len(skills),
        "skills_list": [s["name"] for s in skills[:20]],
        "official_plugins_count": len(plugins),
        "official_plugins_list": [p["name"] for p in plugins[:20]],
    }
