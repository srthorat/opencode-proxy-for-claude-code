import hashlib
import json
import logging
import os
import pathlib
from typing import Any

from .config import GRAPHIFY_GRAPH_PATH

logger = logging.getLogger("opencode-proxy.graphify")

GLOBAL_CACHE_DIR = pathlib.Path.home() / ".opencode-proxy" / "graphs"


def get_workspace_hash(workspace_path: str) -> str:
    """Return MD5 hash of absolute workspace path for global cache lookup."""
    abs_path = os.path.abspath(workspace_path)
    return hashlib.md5(abs_path.encode("utf-8")).hexdigest()


def get_global_graph_path(workspace_path: str) -> pathlib.Path:
    """Return path to global graph cache file for a given workspace path."""
    repo_hash = get_workspace_hash(workspace_path)
    return GLOBAL_CACHE_DIR / f"{repo_hash}.json"


def load_graphify_summary(
    file_path: str | None = None,
    workspace_path: str | None = None,
) -> str:
    """Load and summarize a Graphify knowledge graph JSON file.

    Checks:
    1. Direct `file_path` if provided.
    2. Local workspace directory (`workspace_path / GRAPHIFY_GRAPH_PATH`).
    3. Global centralized cache (`~/.opencode-proxy/graphs/<hash>.json`).

    Returns a formatted markdown string ready for injection into LLM system prompts,
    or an empty string if no valid graph is found.
    """
    target_path: pathlib.Path | None = None

    if file_path:
        p = pathlib.Path(file_path)
        if p.exists():
            target_path = p

    if not target_path and workspace_path:
        p = pathlib.Path(workspace_path) / (os.getenv("GRAPHIFY_GRAPH_PATH") or GRAPHIFY_GRAPH_PATH)
        if p.exists():
            target_path = p
        else:
            global_p = get_global_graph_path(workspace_path)
            if global_p.exists():
                target_path = global_p

    if not target_path:
        default_p = pathlib.Path(os.getenv("GRAPHIFY_GRAPH_PATH") or GRAPHIFY_GRAPH_PATH)
        if default_p.exists():
            target_path = default_p

    if not target_path or not target_path.exists():
        logger.debug("Graphify file not found for file_path=%s, workspace_path=%s", file_path, workspace_path)
        return ""

    try:
        content = target_path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(content)
    except Exception as exc:
        logger.warning("Failed to load Graphify JSON from %s: %s", target_path, exc)
        return ""

    # Parse graph structure (nodes, edges, summary, metadata)
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    summary = data.get("summary", "")

    if not nodes and not summary and not isinstance(data, list):
        return ""

    lines = ["\n--- GRAPHIFY KNOWLEDGE GRAPH CONTEXT ---"]
    if summary:
        lines.append(f"Project Architecture Summary:\n{summary}")

    if isinstance(nodes, list) and nodes:
        lines.append(f"\nIndexed AST Nodes ({len(nodes)} total):")
        for node in nodes[:30]:  # Cap at top 30 key nodes to avoid context bloat
            if isinstance(node, dict):
                label = node.get("label") or node.get("id") or node.get("name")
                ntype = node.get("type") or node.get("kind", "")
                filepath = node.get("file") or node.get("path", "")
                if label:
                    desc = f"- [{ntype}] {label}" if ntype else f"- {label}"
                    if filepath:
                        desc += f" ({filepath})"
                    lines.append(desc)
            elif isinstance(node, str):
                lines.append(f"- {node}")
        if len(nodes) > 30:
            lines.append(f"... and {len(nodes) - 30} more nodes.")

    if isinstance(edges, list) and edges:
        lines.append(f"\nKey Relationships ({len(edges)} total edges):")
        for edge in edges[:20]:  # Cap at top 20 edges
            if isinstance(edge, dict):
                src = edge.get("source") or edge.get("from")
                target = edge.get("target") or edge.get("to")
                rel = edge.get("relation") or edge.get("type", "calls")
                if src and target:
                    lines.append(f"- {src} --[{rel}]--> {target}")
        if len(edges) > 20:
            lines.append(f"... and {len(edges) - 20} more relationships.")

    lines.append("--- END GRAPHIFY CONTEXT ---\n")
    return "\n".join(lines)
