import json
import logging
import pathlib
import sqlite3
import time
from typing import Any

logger = logging.getLogger("opencode-proxy.pattern_memory")

PATTERN_DB_PATH = pathlib.Path.home() / ".opencode-proxy" / "patterns.db"


def _get_conn(db_file: pathlib.Path | None = None) -> sqlite3.Connection:
    target = db_file or PATTERN_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    return conn


def init_pattern_db(db_file: pathlib.Path | None = None) -> None:
    with _get_conn(db_file) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                observed_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS patterns_fts
            USING fts5(description, content='patterns', content_rowid='id')
            """
        )
        conn.commit()


def store_pattern(
    description: str,
    repo: str = "global",
    category: str = "general",
    db_file: pathlib.Path | None = None,
) -> None:
    """Store an observed architectural pattern, recurring bug, or naming convention."""
    try:
        init_pattern_db(db_file)
        with _get_conn(db_file) as conn:
            cur = conn.execute(
                "INSERT INTO patterns (repo, category, description, observed_at) VALUES (?, ?, ?, ?)",
                (repo, category, description, time.time()),
            )
            rowid = cur.lastrowid
            conn.execute("INSERT INTO patterns_fts(rowid, description) VALUES (?, ?)", (rowid, description))
            conn.commit()
    except Exception as exc:
        logger.warning("Pattern store failed: %s", exc)


def search_patterns(query: str, limit: int = 5, db_file: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Full-text search (FTS5/BM25) across all stored codebase patterns."""
    try:
        clean_query = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
        if not clean_query:
            return []
        init_pattern_db(db_file)
        with _get_conn(db_file) as conn:
            rows = conn.execute(
                """
                SELECT p.repo, p.category, p.description, p.observed_at
                FROM patterns_fts f
                JOIN patterns p ON p.id = f.rowid
                WHERE patterns_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (clean_query, limit),
            ).fetchall()
            results = [dict(r) for r in rows]
            if results:
                logger.info("Pattern Memory FTS5 recall: retrieved %d institutional patterns for query %r", len(results), clean_query[:30])
            return results

    except Exception as exc:
        logger.warning("Pattern search failed: %s", exc)
        return []

