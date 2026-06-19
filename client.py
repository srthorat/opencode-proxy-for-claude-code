import logging
from typing import Optional

import httpx

logger = logging.getLogger("opencode-proxy")

_client: Optional[httpx.AsyncClient] = None


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
