"""
opencode-proxy prefetcher
──────────────────────────
Predictive Context Prefetching Engine: Prefetches AST skeletons for files
likely to be referenced in next conversation turns.
"""
import ast
import logging
import os
import pathlib

from .skeletonizer import skeletonize_code

logger = logging.getLogger("opencode-proxy.prefetcher")

_prefetch_cache: dict[str, str] = {}


def prefetch_related_file_skeletons(file_path: str) -> list[str]:
    """Inspect file for imports and prefetch AST skeletons of imported workspace modules."""
    if not file_path or not file_path.endswith(".py") or not os.path.exists(file_path):
        return []

    prefetched: list[str] = []
    base_dir = os.path.dirname(file_path)

    try:
        content = pathlib.Path(file_path).read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                target_rel = node.module.replace(".", "/") + ".py"
                candidate_path = os.path.join(base_dir, target_rel)
                if os.path.exists(candidate_path) and candidate_path not in _prefetch_cache:
                    try:
                        raw = pathlib.Path(candidate_path).read_text(encoding="utf-8", errors="ignore")
                        skel = skeletonize_code(raw)
                        _prefetch_cache[candidate_path] = skel
                        prefetched.append(candidate_path)
                        logger.info("Predictive Prefetcher: Prefetched AST skeleton for %s", candidate_path)
                    except Exception:
                        pass

    except Exception as exc:
        logger.debug("Prefetcher AST scan error for %s: %s", file_path, exc)

    return prefetched
