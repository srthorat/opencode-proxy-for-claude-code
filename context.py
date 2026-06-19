from dataclasses import dataclass
from typing import Optional


@dataclass
class RequestContext:
    """Accumulates state across the forward_request pipeline stages."""

    # Set at creation from the incoming request
    method: str
    path: str
    query: str
    headers: dict
    body: bytes
    content_type: str

    # Routing / upstream target — initialised with global defaults, then
    # overwritten by _sanitize_and_route if the payload carries a model field.
    per_request_upstream_url: str = ""
    per_request_upstream_api_key: Optional[str] = None

    # Set during _sanitize_and_route
    resolved_model: Optional[str] = None
    is_direct: bool = False

    # Set after routing: body that will actually be sent to the upstream
    send_content: Optional[bytes] = None

    # Set during _maybe_convert_protocol
    need_protocol_conv: bool = False
    pre_conv_content: Optional[bytes] = None  # send_content before Anthropic→OpenAI conversion

    # Set during _build_target_url
    target_url: Optional[str] = None
