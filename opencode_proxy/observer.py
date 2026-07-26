import json
import logging
import os
import re
from typing import Any

from .memory_db import record_graph_node, record_observation

logger = logging.getLogger("opencode-proxy.observer")

# Regex to detect python/rust/js function and class definitions
SYMBOL_REGEX = re.compile(
    r"\b(?:def|class|fn|function|struct|enum|interface|trait)\s+([A-Za-z0-9_]+)",
    re.MULTILINE,
)


def observe_payload(payload: dict[str, Any], workspace_path: str | None = None) -> None:
    """Inspect request payload for tool usage and code snippets, recording memories automatically."""
    if not isinstance(payload, dict):
        return

    target_workspace = workspace_path or os.getcwd()
    messages = payload.get("messages", [])

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        content = msg.get("content", "")

        # Handle list of blocks (tool_use, tool_result, text)
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue

                btype = block.get("type")

                # Handle tool call usage
                if btype == "tool_use":
                    tname = block.get("name", "")
                    tinput = block.get("input", {})
                    _process_tool_use(tname, tinput, target_workspace)

                # Handle tool call results
                elif btype == "tool_result":
                    res_content = block.get("content", "")
                    _process_tool_result(res_content, target_workspace)

        elif isinstance(content, str) and content:
            _extract_symbols(content, target_workspace)


def _process_tool_use(tool_name: str, tool_input: dict[str, Any], workspace_path: str) -> None:
    if not isinstance(tool_input, dict):
        return

    filepath = (
        tool_input.get("TargetFile")
        or tool_input.get("path")
        or tool_input.get("file")
        or tool_input.get("AbsolutePath")
    )

    if filepath and isinstance(filepath, str):
        record_graph_node(
            workspace_path=workspace_path,
            node_label=os.path.basename(filepath),
            node_type="file",
            file_path=filepath,
        )
        record_observation(
            workspace_path=workspace_path,
            content=f"Accessed or modified file via {tool_name}",
            file_path=filepath,
            category="file_access",
        )


def _process_tool_result(result_content: Any, workspace_path: str) -> None:
    text = ""
    if isinstance(result_content, str):
        text = result_content
    elif isinstance(result_content, list):
        for sub in result_content:
            if isinstance(sub, dict) and sub.get("type") == "text":
                text += sub.get("text", "") + "\n"

    if text:
        _extract_symbols(text, workspace_path)


def _extract_symbols(text: str, workspace_path: str) -> None:
    matches = SYMBOL_REGEX.findall(text)
    for match in matches[:10]:  # Limit per payload
        if len(match) > 2:
            record_graph_node(
                workspace_path=workspace_path,
                node_label=match,
                node_type="symbol",
            )
