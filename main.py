import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from client import close_client
from config import UPSTREAM_URL, PORT
from forward import forward_request
from observability.stats import snapshot
from auth import check_auth
from config import PROXY_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opencode-proxy")


# ---------------------------------------------------------------------------
# P2 #10: Lifespan context manager (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — startup is implicit (nothing to do); shutdown closes the
    shared httpx client after a brief drain window for in-flight requests."""
    if not PROXY_API_KEY:
        logger.warning(
            "PROXY_API_KEY is not set — proxy accepts requests from any client. "
            "Set PROXY_API_KEY in .env to require inbound authentication."
        )
    yield  # startup: nothing needed — client is created lazily on first request
    await asyncio.sleep(0.5)
    await close_client()


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request size limit middleware
# ---------------------------------------------------------------------------

MAX_REQUEST_BYTES = 50 * 1024 * 1024  # 50 MB — reasonable cap for LLM payloads with images


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            return JSONResponse({"error": "request too large"}, status_code=413)
        return await call_next(request)


app.add_middleware(RequestSizeLimitMiddleware)


# ---------------------------------------------------------------------------
# Health / liveness
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "upstream": UPSTREAM_URL}


@app.get("/admin/stats")
async def admin_stats(request: Request):
    """In-memory request stats — gated behind PROXY_API_KEY if set."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err
    return snapshot()


@app.head("/")
@app.head("/{path:path}")
async def head_liveness(path: str = ""):
    """Respond 200 to HEAD probes (Headroom upstream health checks)."""
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Token count estimation
# ---------------------------------------------------------------------------

@app.post("/v1/messages/count_tokens")
async def count_tokens_endpoint(request: Request):
    """Local token count estimation — upstream doesn't support this endpoint.

    Approximates using ~3.5 chars/token, which is accurate enough for Claude Code
    to make context-window decisions without hitting a non-existent upstream route.
    """
    try:
        content = await request.body()
        payload = json.loads(content.decode("utf-8"))
    except Exception as exc:
        logger.warning("count_tokens: failed to parse request body: %s", exc)
        return JSONResponse({"input_tokens": 0})

    total_chars = 0

    system = payload.get("system", "")
    if isinstance(system, str):
        total_chars += len(system)
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                total_chars += len(block.get("text", ""))

    for msg in payload.get("messages", []):
        msg_content = msg.get("content", "")
        if isinstance(msg_content, str):
            total_chars += len(msg_content)
        elif isinstance(msg_content, list):
            for block in msg_content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    total_chars += len(block.get("text", ""))
                elif btype in ("tool_use", "tool_result"):
                    total_chars += len(json.dumps(block))

    for tool in payload.get("tools", []):
        total_chars += len(json.dumps(tool))

    estimated_tokens = max(1, int(total_chars / 3.5))
    logger.info("count_tokens: estimated %d tokens from %d chars", estimated_tokens, total_chars)
    return JSONResponse({"input_tokens": estimated_tokens})


# ---------------------------------------------------------------------------
# Catch-all proxy route
# ---------------------------------------------------------------------------

@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy(path: str, request: Request):
    return await forward_request(request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
