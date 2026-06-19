"""TypedDict definitions for the main Anthropic API payload shapes.

These types serve as a reference for future contributors.  They are not
enforced at runtime — Python's duck-typing is preserved throughout the codebase
— but they make IDE autocompletion and mypy checks meaningful.

Usage example (annotation-only; does not change runtime behaviour):
    from types import AnthropicPayload
    def _sanitize_messages(messages: list, payload: AnthropicPayload) -> list: ...
"""

from typing import List, Optional, TypedDict, Union


class MessageBlock(TypedDict, total=False):
    """A single content block inside an Anthropic message."""

    type: str                           # "text" | "tool_use" | "tool_result" | "image" | …
    text: str                           # present when type == "text"
    id: str                             # tool_use block identifier (e.g. "toolu_…")
    name: str                           # tool name (type == "tool_use")
    input: dict                         # tool input dict (type == "tool_use")
    tool_use_id: str                    # back-reference in tool_result blocks
    content: Union[str, List[dict]]     # tool_result content (str or block list)


class AnthropicPayload(TypedDict, total=False):
    """Top-level Anthropic Messages API request payload."""

    model: str
    messages: List[dict]
    system: Union[str, List[dict]]      # string or list of text blocks
    max_tokens: int
    stream: bool
    tools: List[dict]
    tool_choice: Union[str, dict]       # "auto" | "any" | {"type":"tool","name":…}
    thinking: dict                      # extended-thinking params (stripped by proxy)
    betas: list                         # Anthropic beta flags (stripped by proxy)
    temperature: float
    top_p: float
    stop: Union[str, List[str]]
