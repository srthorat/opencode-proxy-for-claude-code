"""
opencode-proxy http_utils
──────────────────────────
Merged from: client.py · auth.py

Shared HTTP plumbing: the singleton async httpx client and Bearer token
authentication check used by the FastAPI entry-point.
"""
import hmac
import logging

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from .config import PROXY_API_KEY

logger = logging.getLogger("opencode-proxy")

# ── Shared async httpx client ────────────────────────────────────────────────

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    """Return the module-level shared httpx client, creating it if necessary."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _client


async def close_client() -> None:
    """Close the shared httpx client. Called during application shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        logger.info("Shared httpx client closed")


# ── Bearer token auth ────────────────────────────────────────────────────────

def check_auth(request: Request) -> JSONResponse | None:
    """Return a 401 JSONResponse if inbound auth fails, or None to allow through.

    Only active when PROXY_API_KEY is configured.
    Uses hmac.compare_digest for timing-safe comparison.
    """
    if not PROXY_API_KEY:
        return None
    auth_header = request.headers.get("authorization", "")
    provided = auth_header[len("Bearer "):].strip() if auth_header.startswith("Bearer ") else ""
    if not hmac.compare_digest(provided.encode(), PROXY_API_KEY.encode()):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None
