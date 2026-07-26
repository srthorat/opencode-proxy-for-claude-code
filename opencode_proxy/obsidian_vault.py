"""
opencode-proxy obsidian_vault
──────────────────────────────
Obsidian Knowledge Vault Manager: Auto-syncs Architectural Decision Records (ADRs),
Pattern Memory, and Tech Debt reports into an Obsidian Markdown Vault with [[wiki-links]].
"""
import logging
import os
import pathlib
import time

logger = logging.getLogger("opencode-proxy.obsidian_vault")

DEFAULT_VAULT_DIR = pathlib.Path.home() / ".obsidian_vault" / "opencode"


def ensure_vault_structure(vault_dir: pathlib.Path | None = None) -> pathlib.Path:
    """Ensure Obsidian vault directories exist."""
    target_dir = vault_dir or DEFAULT_VAULT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "Architecture").mkdir(exist_ok=True)
    (target_dir / "TechDebt").mkdir(exist_ok=True)
    (target_dir / "Patterns").mkdir(exist_ok=True)
    return target_dir


def sync_adr_to_obsidian(title: str, content: str, vault_dir: pathlib.Path | None = None) -> str:
    """Sync an Architectural Decision Record to Obsidian with [[wiki-links]]."""
    v_dir = ensure_vault_structure(vault_dir)
    safe_title = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in title).strip()
    file_path = v_dir / "Architecture" / f"{safe_title}.md"

    obsidian_content = (
        f"# [[{safe_title}]]\n\n"
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Tags**: #architecture #adr #opencode-proxy\n\n"
        f"{content}\n\n"
        f"--- \n"
        f"Related Notes: [[Architecture Index]] | [[Tech Debt Summary]]\n"
    )

    try:
        file_path.write_text(obsidian_content, encoding="utf-8")
        logger.info("Obsidian Vault: Synced ADR note to %s", file_path)
        return str(file_path)
    except Exception as exc:
        logger.warning("Obsidian Vault sync failed: %s", exc)
        return ""


def get_obsidian_vault_summary(vault_dir: pathlib.Path | None = None) -> str:
    """Return summary of Obsidian Knowledge Vault notes for prompt context."""
    v_dir = vault_dir or DEFAULT_VAULT_DIR
    if not v_dir.exists():
        return ""

    try:
        notes = list(v_dir.rglob("*.md"))
        if not notes:
            return ""

        note_names = [n.stem for n in notes[:5]]
        wiki_links = " | ".join(f"[[{n}]]" for n in note_names)
        return (
            "\n--- OBSIDIAN KNOWLEDGE VAULT INTEGRATION ---\n"
            f"Active Obsidian Vault Notes: {wiki_links}\n"
            "--- END OBSIDIAN VAULT ---\n"
        )
    except Exception:
        return ""
