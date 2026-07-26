import hashlib
import json
import logging
import pathlib
import sqlite3
import time
from typing import Any

logger = logging.getLogger("opencode-proxy.response_cache")

CACHE_DIR = pathlib.Path.home() / ".opencode-proxy"
CACHE_DB_PATH = CACHE_DIR / "cache.db"


def get_cache_connection(db_file: pathlib.Path | None = None) -> sqlite3.Connection:
    target_path = db_file or CACHE_DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_cache_db(db_file: pathlib.Path | None = None) -> None:
    with get_cache_connection(db_file) as conn:
        conn.cursor().execute(
            """
            CREATE TABLE IF NOT EXISTS response_cache (
                prompt_hash TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.commit()


def hash_payload(payload: dict[str, Any]) -> str:
    """Generate SHA-256 hash for deterministic payload caching."""
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_response(payload: dict[str, Any], db_file: pathlib.Path | None = None) -> dict[str, Any] | None:
    """Retrieve cached response for identical prompts (0ms latency & 0 token cost)."""
    try:
        init_cache_db(db_file)
        phash = hash_payload(payload)
        with get_cache_connection(db_file) as conn:
            row = conn.cursor().execute(
                "SELECT response_json FROM response_cache WHERE prompt_hash = ?", (phash,)
            ).fetchone()
            if row:
                logger.info("Response Cache HIT for hash: %s (0ms latency)", phash[:8])
                return json.loads(row["response_json"])
    except Exception as exc:
        logger.warning("Cache lookup failed: %s", exc)
    return None


def store_cached_response(payload: dict[str, Any], model: str, response_data: dict[str, Any], db_file: pathlib.Path | None = None) -> None:
    """Store LLM response into cache database."""
    try:
        init_cache_db(db_file)
        phash = hash_payload(payload)
        with get_cache_connection(db_file) as conn:
            conn.cursor().execute(
                """
                INSERT INTO response_cache (prompt_hash, model, response_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(prompt_hash) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (phash, model, json.dumps(response_data), time.time()),
            )
            conn.commit()
            logger.info("Stored response in cache for hash: %s", phash[:8])
    except Exception as exc:
        logger.warning("Cache store failed: %s", exc)
