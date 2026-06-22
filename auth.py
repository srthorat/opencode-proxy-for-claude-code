import hmac
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from config import PROXY_API_KEY

logger = logging.getLogger("opencode-proxy")


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
