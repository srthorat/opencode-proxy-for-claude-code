"""
opencode-proxy ccr_archive
───────────────────────────
Engine 2: Content-Context Retrieval (CCR) Archive Markers Engine.
Archives large tool outputs (> 30,000 chars) into local SQLite store
and replaces payload with light reference markers.
"""
import hashlib
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("opencode-proxy.ccr_archive")

DB_PATH = Path.home() / ".opencode-proxy" / "ccr_archive.db"


def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ccr_store (
                key TEXT PRIMARY KEY,
                content TEXT,
                char_len INTEGER,
                line_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


_init_db()


def archive_large_content(content: str, threshold: int = 30000) -> str:
    """Archive content exceeding threshold and return light CCR reference marker."""
    if not content or not isinstance(content, str) or len(content) <= threshold:
        return content

    char_len = len(content)
    line_count = len(content.splitlines())
    key_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ccr_store (key, content, char_len, line_count) VALUES (?, ?, ?, ?)",
                (key_hash, content, char_len, line_count),
            )
            conn.commit()
    except Exception as e:
        logger.warning("CCR archiving database error: %s", e)
        return content

    logger.info("CCR Archived large block: key=%s, len=%d chars", key_hash, char_len)
    return (
        f"[CCR_ARCHIVED: key={key_hash} | length={char_len} chars | lines={line_count} lines. "
        f"Content safely archived in local proxy memory.]"
    )


def fetch_archived_content(key_hash: str) -> str | None:
    """Retrieve archived content from CCR database by key hash."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM ccr_store WHERE key = ?", (key_hash,))
            row = cursor.fetchone()
            if row:
                return row[0]
    except Exception as e:
        logger.warning("CCR fetch error for key %s: %s", key_hash, e)
    return None
