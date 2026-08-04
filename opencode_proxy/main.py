from __future__ import annotations

import asyncio
import json
import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from starlette.middleware.base import BaseHTTPMiddleware

from .http_utils import check_auth, close_client
from .config import (
    PORT,
    PROXY_API_KEY,
    UPSTREAM_URL,
)
from .forward import forward_request
from .key_pool import pool
from .proxy_manager import proxy_updater_task, init_proxies





logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opencode-proxy")


# ---------------------------------------------------------------------------
# P2 #10: Lifespan context manager (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — auto-initialise ALL subsystems at startup, then serve."""
    # ── 1. Auth warning ────────────────────────────────────────────────────
    if not PROXY_API_KEY:
        logger.warning(
            "PROXY_API_KEY is not set — proxy accepts requests from any client. "
            "Set PROXY_API_KEY in .env to require inbound authentication."
        )

    # ── 1.5. Initialize Proxy Pool ──────────────────────────────────────────
    logger.info("[Init] Fetching and verifying initial proxy pool …")
    await init_proxies()



    # ── 4. LLM key pool probe ──────────────────────────────────────────────
    logger.info("[Init] Probing all upstream LLM API keys …")
    await pool.probe_all()

    # ── 5. Background key re-probe loops & Proxy updater ──────────────────
    _recheck_task = asyncio.create_task(pool.recheck_loop(interval=60))

    _proxy_task = asyncio.create_task(proxy_updater_task())


    # ── 6. Startup banner ─────────────────────────────────────────────────
    logger.info(
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║       opencode-proxy  ✓  ALL SYSTEMS READY           ║\n"
        "║  Upstream LLM  : %s\n"
        "║  Free models   : mimo-v2.5-free → north-mini-code-free → free-auto\n"
        "║  Port          : %d\n"
        "╚══════════════════════════════════════════════════════╝",
        UPSTREAM_URL,
        PORT,
    )

    yield  # ── server is live, handle requests ──────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────
    _recheck_task.cancel()
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
@app.get("/admin/health")
async def healthz():
    """Simple readiness health check."""
    return {
        "status": "ok",
        "proxy_server": True,
        "upstream": UPSTREAM_URL,
    }








@app.get("/admin/key-health")
async def admin_key_health(request: Request):
    """Free-auto key pool health — shows per-model key status by index.
    Raw key values are never returned, only their 1-based indices.
    Gated behind PROXY_API_KEY if set.
    """
    auth_err = check_auth(request)
    if auth_err:
        return auth_err
    return {
        "opencode": pool.health_snapshot(),
    }


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
