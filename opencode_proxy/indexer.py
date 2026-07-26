import json
import logging
import os
import pathlib
import re
import threading
from typing import Any

from .graphify import get_global_graph_path

logger = logging.getLogger("opencode-proxy.indexer")

# File extensions to auto-index for codebase graph
INDEX_EXTENSIONS = {".py", ".rs", ".js", ".ts", ".jsx", ".tsx", ".go", ".sql", ".md"}

# Regex patterns for fast AST symbol extraction across languages
SYMBOL_PATTERNS = [
    re.compile(r"\b(?:def|class)\s+([A-Za-z0-9_]+)", re.MULTILINE),  # Python
    re.compile(r"\b(?:fn|struct|enum|trait|impl)\s+([A-Za-z0-9_]+)", re.MULTILINE),  # Rust
    re.compile(r"\b(?:function|interface|type|class)\s+([A-Za-z0-9_]+)", re.MULTILINE),  # JS/TS
    re.compile(r"\b(?:type|struct|interface)\s+([A-Za-z0-9_]+)\s+struct", re.MULTILINE),  # Go
    re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_\.\"]+)", re.IGNORECASE),  # SQL
]

_indexing_lock = threading.Lock()
_indexed_workspaces: set[str] = set()


def ensure_workspace_indexed(workspace_path: str | None = None) -> None:
    """Ensure workspace AST graph is indexed in background thread without blocking request flow."""
    if not workspace_path or not os.path.isdir(workspace_path):
        return

    abs_path = os.path.abspath(workspace_path)

    with _indexing_lock:
        if abs_path in _indexed_workspaces:
            return
        _indexed_workspaces.add(abs_path)

    # Launch background thread to build/refresh workspace graph
    thread = threading.Thread(target=_index_workspace_background, args=(abs_path,), daemon=True)
    thread.start()


def _index_workspace_background(workspace_path: str) -> None:
    """Walk workspace files and build AST knowledge graph JSON in global cache directory."""
    try:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        target_dir = pathlib.Path(workspace_path)
        file_count = 0

        for root, dirs, files in os.walk(workspace_path):
            # Skip common noise/build directories
            dirs[:] = [
                d
                for d in dirs
                if d
                not in (
                    ".git",
                    ".venv",
                    "venv",
                    "node_modules",
                    "__pycache__",
                    "target",
                    "dist",
                    "build",
                    ".mypy_cache",
                    ".pytest_cache",
                )
            ]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in INDEX_EXTENSIONS:
                    continue

                file_count += 1
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, workspace_path)

                # Add file node
                nodes.append(
                    {
                        "id": rel_path,
                        "label": fname,
                        "type": "file",
                        "path": rel_path,
                    }
                )

                # Parse AST symbols
                try:
                    content = pathlib.Path(full_path).read_text(encoding="utf-8", errors="ignore")
                    for pattern in SYMBOL_PATTERNS:
                        for match in pattern.findall(content):
                            if isinstance(match, str) and len(match) > 2:
                                node_id = f"{rel_path}:{match}"
                                nodes.append(
                                    {
                                        "id": node_id,
                                        "label": match,
                                        "type": "symbol",
                                        "file": rel_path,
                                    }
                                )
                                edges.append(
                                    {
                                        "source": rel_path,
                                        "target": match,
                                        "relation": "defines",
                                    }
                                )
                except Exception as file_exc:
                    logger.debug("Failed to index file %s: %s", full_path, file_exc)

        graph_data = {
            "summary": f"Auto-indexed codebase graph for {os.path.basename(workspace_path)} ({file_count} files, unlimited memory capacity).",
            "nodes": nodes,
            "edges": edges,
        }



        # Write to global cache file ~/.opencode-proxy/graphs/<repo_hash>.json
        global_path = get_global_graph_path(workspace_path)
        global_path.parent.mkdir(parents=True, exist_ok=True)
        global_path.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")
        logger.info("Successfully auto-indexed graph for %s (%d nodes) at %s", workspace_path, len(nodes), global_path)

    except Exception as exc:
        logger.warning("Auto-indexing failed for %s: %s", workspace_path, exc)


# ── Monorepo Symbol Search (merged from monorepo_linker.py) ──────────────────

GRAPHS_DIR = pathlib.Path.home() / ".opencode-proxy" / "graphs"


def search_monorepo_symbols(symbol_query: str, graphs_dir: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Search cross-repo AST symbol definitions across all indexed repositories in monorepos."""
    target_dir = graphs_dir or GRAPHS_DIR
    if not target_dir.exists() or not symbol_query:
        return []

    results: list[dict[str, Any]] = []
    query_lower = symbol_query.lower()

    try:
        for json_file in target_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8", errors="ignore"))
                summary = data.get("summary", "")
                nodes = data.get("nodes", [])
                for node in nodes:
                    lbl = str(node.get("label", "")).lower()
                    if query_lower in lbl:
                        results.append({
                            "symbol": node.get("label"),
                            "type": node.get("type"),
                            "file": node.get("file") or node.get("path"),
                            "graph": json_file.name,
                            "summary": summary,
                        })
                        if len(results) >= 20:
                            break
            except Exception:
                pass
            if len(results) >= 20:
                break
    except Exception as exc:
        logger.warning("Failed monorepo symbol search: %s", exc)

    return results


def link_monorepo_context(user_text: str, graphs_dir: pathlib.Path | None = None) -> str:
    """Analyze prompt for code symbols and resolve cross-repository definitions from monorepo graphs."""
    if not user_text or not user_text.strip():
        return ""

    # Extract potential symbol words (CamelCase or snake_case or function calls)
    words = re.findall(r"\b[A-Za-z0-9_]{4,}\b", user_text)
    symbols = [w for w in words if "_" in w or any(c.isupper() for c in w[1:])]
    if not symbols:
        return ""

    matched_results: list[dict[str, Any]] = []
    for sym in symbols[:3]:
        res = search_monorepo_symbols(sym, graphs_dir=graphs_dir)
        if res:
            matched_results.extend(res[:2])

    if not matched_results:
        return ""

    lines = ["\n--- MONOREPO CROSS-REPOSITORY SYMBOL LINKER ---"]
    for item in matched_results[:5]:
        sym = item.get("symbol", "")
        stype = item.get("type", "symbol")
        file_path = item.get("file", "")
        graph = item.get("graph", "")
        lines.append(f"  • [{stype}] {sym} in {file_path} (Repo Graph: {graph})")

    lines.append("--- END MONOREPO SYMBOLS ---\n")
    return "\n".join(lines)


