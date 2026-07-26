import logging
import os
import pathlib
import sqlite3
import time
from typing import Any

logger = logging.getLogger("opencode-proxy.memory_db")

DB_DIR = pathlib.Path.home() / ".opencode-proxy"
DB_PATH = DB_DIR / "memory.db"


def get_connection(db_file: pathlib.Path | None = None) -> sqlite3.Connection:
    target_path = db_file or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_file: pathlib.Path | None = None) -> None:
    """Initialize SQLite database tables for workspace memories and code graphs."""
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_path TEXT NOT NULL,
                file_path TEXT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_path TEXT NOT NULL,
                node_label TEXT NOT NULL,
                node_type TEXT,
                file_path TEXT,
                updated_at REAL NOT NULL,
                UNIQUE(workspace_path, node_label, file_path)
            )
            """
        )
        conn.commit()


MAX_MEMORY_LINES = None  # Unlimited memory retention capacity per workspace


def record_observation(
    workspace_path: str,
    content: str,
    file_path: str | None = None,
    category: str = "general",
    db_file: pathlib.Path | None = None,
) -> None:
    """Record a codebase observation into SQLite database with unlimited retention."""
    if not workspace_path or not content:
        return
    try:
        init_db(db_file)
        with get_connection(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO observations (workspace_path, file_path, category, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_path, file_path, category, content, time.time()),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Failed to record memory observation: %s", exc)


def record_graph_node(
    workspace_path: str,
    node_label: str,
    node_type: str = "symbol",
    file_path: str | None = None,
    db_file: pathlib.Path | None = None,
) -> None:
    """Record or update a code graph node into SQLite database with unlimited retention."""
    if not workspace_path or not node_label:
        return
    try:
        init_db(db_file)
        with get_connection(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO graph_nodes (workspace_path, node_label, node_type, file_path, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workspace_path, node_label, file_path) DO UPDATE SET
                    node_type = excluded.node_type,
                    updated_at = excluded.updated_at
                """,
                (workspace_path, node_label, node_type, file_path, time.time()),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Failed to record graph node: %s", exc)


def get_workspace_memory_summary(
    workspace_path: str | None = None,
    db_file: pathlib.Path | None = None,
    limit: int = 100,
) -> str:
    """Retrieve and format past observations and graph nodes for a workspace with unlimited capacity.

    Returns a markdown summary ready for system-prompt injection.
    """
    if not workspace_path:
        return ""


    try:
        init_db(db_file)
        with get_connection(db_file) as conn:
            cursor = conn.cursor()
            obs_rows = cursor.execute(
                """
                SELECT file_path, category, content FROM observations
                WHERE workspace_path = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (workspace_path, limit),
            ).fetchall()

            node_rows = cursor.execute(
                """
                SELECT node_label, node_type, file_path FROM graph_nodes
                WHERE workspace_path = ?
                ORDER BY updated_at DESC LIMIT 50
                """,
                (workspace_path,),
            ).fetchall()


        if not obs_rows and not node_rows:
            return ""

        lines = ["\n--- PROXY SERVER MEMORY & CODEBASE CONTEXT ---"]

        if node_rows:
            lines.append("Observed Code Architecture & Symbols:")
            for row in node_rows:
                lbl = row["node_label"]
                ntype = row["node_type"] or "symbol"
                fp = row["file_path"]
                desc = f"- [{ntype}] {lbl}"
                if fp:
                    desc += f" ({fp})"
                lines.append(desc)

        if obs_rows:
            lines.append("\nRecent Codebase Observations:")
            for row in obs_rows:
                cat = row["category"]
                fp = row["file_path"]
                cnt = row["content"]
                prefix = f"[{cat}]" if cat else ""
                if fp:
                    prefix += f" {fp}:"
                lines.append(f"- {prefix} {cnt[:150]}")

        lines.append("--- END PROXY MEMORY CONTEXT ---\n")
        return "\n".join(lines)

    except Exception as exc:
        logger.warning("Failed to get workspace memory summary: %s", exc)
        return ""
