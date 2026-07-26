"""
opencode-proxy query_optimizer
───────────────────────────────
Database Query Optimizer Skill: Analyzes SQL queries, indexing strategies,
and EXPLAIN plans for 10x database performance.
"""
import logging
import re

logger = logging.getLogger("opencode-proxy.query_optimizer")

SQL_PATTERNS = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|JOIN|GROUP BY|ORDER BY|WHERE|HAVING)\b", re.I)


def is_sql_query_present(user_text: str) -> bool:
    """Return True if user text contains SQL query statements."""
    if not user_text or not isinstance(user_text, str):
        return False
    matches = SQL_PATTERNS.findall(user_text)
    return len(matches) >= 2


def get_query_optimization_context(user_text: str) -> str:
    """Inject database query optimization guidelines into prompt context."""
    if not is_sql_query_present(user_text):
        return ""

    logger.info("Database Query Optimizer Skill auto-activated.")
    return (
        "\n--- DATABASE QUERY OPTIMIZER SKILL ACTIVE ---\n"
        "- Indexing Strategy: Enforce composite B-Tree indexes on WHERE and JOIN columns.\n"
        "- Query Efficiency: Avoid 'SELECT *'; specify required columns explicitly.\n"
        "- EXPLAIN Plan Analysis: Inspect query execution plans for Sequential Scans vs Index Scans.\n"
        "- N+1 Query Prevention: Use JOIN FETCH or eager loading to eliminate N+1 ORM queries.\n"
        "--- END QUERY OPTIMIZER ---\n"
    )
