from __future__ import annotations

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

import asyncio

_client_pool: dict[str | None, httpx.AsyncClient] = {}


async def get_client(proxy_url: str | None = None) -> httpx.AsyncClient:
    """Return the module-level shared httpx client for the given proxy, creating it if necessary."""
    global _client_pool
    client = _client_pool.get(proxy_url)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        _client_pool[proxy_url] = client
        
        # Enforce LRU limit to prevent memory leaks from thousands of proxies
        if len(_client_pool) > 50:
            oldest_key = next(iter(_client_pool))
            old_client = _client_pool.pop(oldest_key)
            if not old_client.is_closed:
                asyncio.create_task(old_client.aclose())
                
    return client


async def close_client() -> None:
    """Close all shared httpx clients. Called during application shutdown."""
    global _client_pool
    for proxy_url, client in _client_pool.items():
        if client is not None and not client.is_closed:
            await client.aclose()
    _client_pool.clear()
    logger.info("Shared httpx clients closed")


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
