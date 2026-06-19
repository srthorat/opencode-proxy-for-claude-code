import json
import logging
import time
import uuid

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse, JSONResponse

from auth import check_auth
from client import get_client
from config import UPSTREAM_URL, UPSTREAM_API_KEY, _ANTHROPIC_COMPAT_MODELS
from context import RequestContext
from conversion.request import _anthropic_to_openai
from conversion.response import _openai_to_anthropic
from conversion.streaming import _openai_stream_to_anthropic
from router import auto_select_model, resolve_model_config, map_claude_model_name, get_fallbacks
from sanitization import _sanitize_messages

logger = logging.getLogger("opencode-proxy")

# Headers dropped from inbound requests before forwarding upstream.
# anthropic-beta carries beta flags (e.g. interleaved-thinking-2025-05-14) that
# OpenCode does not support; anthropic-version is Anthropic-specific.
_DROP_HEADERS = {"host", "anthropic-beta", "anthropic-version"}
_STRIP_QS = {"beta", "betas"}
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_openai_compat(model_name: str) -> bool:
    """Return True when the model uses OpenAI /chat/completions format."""
    return model_name not in _ANTHROPIC_COMPAT_MODELS


# ---------------------------------------------------------------------------
# Pipeline stage 1: parse body, sanitize messages, resolve model
# ---------------------------------------------------------------------------

async def _sanitize_and_route(ctx: RequestContext) -> None:
    """Parse the JSON body, sanitize messages, resolve the upstream model and URL.

    Populates ctx.send_content, ctx.resolved_model, ctx.per_request_upstream_url,
    ctx.per_request_upstream_api_key, and ctx.is_direct.
    """
    ctx.send_content = ctx.body

    if not (ctx.content_type.startswith("application/json") and ctx.body):
        return

    try:
        payload = json.loads(ctx.body.decode("utf-8"))
        if not isinstance(payload, dict):
            return

        if "messages" in payload:
            payload["messages"] = _sanitize_messages(payload["messages"], payload)

        # Strip extended-thinking / betas fields unsupported by OpenCode
        payload.pop("betas", None)
        payload.pop("thinking", None)

        if "model" in payload:
            incoming_model = payload["model"]
            _model_lower = str(incoming_model).strip().lower()

            if not _model_lower.startswith("direct:"):
                # Map claude-* model names to routing tokens when not in MODEL_MAP
                if _model_lower.startswith("claude-"):
                    mapped = map_claude_model_name(incoming_model)
                    if mapped != incoming_model:
                        logger.info("Claude model %r → %s", incoming_model, mapped)
                        incoming_model = mapped
                        _model_lower = mapped

                # Dynamic routing: auto / free-auto / go-auto
                if _model_lower in ("auto", "free-auto", "go-auto"):
                    messages = payload.get("messages", [])
                    _forced_tier = {"free-auto": "free", "go-auto": "go"}.get(_model_lower)
                    _has_tools = bool(payload.get("tools"))  # agent mode signal
                    incoming_model = await auto_select_model(
                        messages, forced_tier=_forced_tier, has_tools=_has_tools
                    )
                    payload["model"] = incoming_model

            upstream_model, upstream_url, upstream_api_key, role = resolve_model_config(
                incoming_model
            )
            ctx.is_direct = role == "direct"
            payload["model"] = upstream_model
            ctx.resolved_model = upstream_model
            ctx.per_request_upstream_url = upstream_url or UPSTREAM_URL
            ctx.per_request_upstream_api_key = upstream_api_key or UPSTREAM_API_KEY

        ctx.send_content = json.dumps(payload).encode("utf-8")

    except Exception as e:
        logger.exception("Payload processing error (leaving body as-is)")


# ---------------------------------------------------------------------------
# Pipeline stage 2: Anthropic → OpenAI protocol conversion (if needed)
# ---------------------------------------------------------------------------

async def _maybe_convert_protocol(ctx: RequestContext) -> None:
    """Convert the Anthropic /v1/messages payload to OpenAI /chat/completions format.

    Sets ctx.need_protocol_conv and rewrites ctx.send_content if conversion is needed.
    """
    ctx.need_protocol_conv = (
        ctx.path == "/v1/messages"
        and ctx.resolved_model is not None
        and _is_openai_compat(ctx.resolved_model)
        and not ctx.is_direct  # direct-provider: client speaks the provider's native protocol
    )

    if not ctx.need_protocol_conv:
        return
    if not (ctx.content_type.startswith("application/json") and ctx.send_content):
        return

    ctx.pre_conv_content = ctx.send_content  # saved for fallback re-conversion
    try:
        oai_payload = _anthropic_to_openai(json.loads(ctx.send_content.decode("utf-8")))
        ctx.send_content = json.dumps(oai_payload).encode("utf-8")
        logger.info("Protocol: Anthropic→OpenAI for model=%s", ctx.resolved_model)
    except Exception as exc:
        logger.error("Anthropic→OpenAI conversion failed: %s", exc)
        ctx.need_protocol_conv = False


# ---------------------------------------------------------------------------
# Pipeline stage 3: build the target URL
# ---------------------------------------------------------------------------

def _build_target_url(ctx: RequestContext) -> None:
    """Compute ctx.target_url and potentially rewrite ctx.send_content for legacy paths."""
    base = ctx.per_request_upstream_url.rstrip("/")
    path = ctx.path

    if ctx.need_protocol_conv and path == "/v1/messages":
        path = "/chat/completions"
    elif path.startswith("/v1/completions"):
        path = path.replace("/v1/completions", "/chat/completions", 1)
        # Convert legacy completions prompt→messages format
        if ctx.content_type.startswith("application/json") and ctx.send_content:
            try:
                p = json.loads(ctx.send_content.decode("utf-8"))
                if isinstance(p, dict) and "prompt" in p and "messages" not in p:
                    prompt_val = p.pop("prompt")
                    p["messages"] = [{"role": "user", "content": prompt_val}]
                    ctx.send_content = json.dumps(p).encode("utf-8")
                    ctx.headers["content-length"] = str(len(ctx.send_content))
            except Exception as e:
                logger.exception("Legacy completions path rewrite failed")
    elif path.startswith("/v1/chat/completions"):
        path = path.replace("/v1/chat/completions", "/chat/completions", 1)

    # If base already includes /v1 and path also starts with /v1, avoid duplication
    if base.endswith("/v1") and path.startswith("/v1"):
        path = path[len("/v1"):]

    target_url = base + path
    # Collapse accidental duplicate version segments like /v1/v1/ → /v1/
    target_url = target_url.replace("/v1/v1/", "/v1/")

    if ctx.query:
        qs_parts = [
            p for p in ctx.query.split("&")
            if p.split("=")[0].lower() not in _STRIP_QS
        ]
        if qs_parts:
            target_url += "?" + "&".join(qs_parts)

    ctx.target_url = target_url


# ---------------------------------------------------------------------------
# Pipeline stage 4: forward to upstream, handle response
# ---------------------------------------------------------------------------

async def _forward_to_upstream(ctx: RequestContext) -> Response:
    """Send the request upstream, retrying configured fallback models on retryable errors."""
    req_id = ctx.headers.get("x-request-id")

    # Build ordered candidate list: [primary, fallback1, fallback2, ...]
    candidates: list[tuple[str, str, str | None, bool]] = [
        (ctx.resolved_model or "", ctx.per_request_upstream_url,
         ctx.per_request_upstream_api_key, ctx.need_protocol_conv)
    ]
    if ctx.resolved_model:
        for fb in get_fallbacks(ctx.resolved_model):
            fb_model, fb_url, fb_key, _ = resolve_model_config(fb)
            fb_need_conv = (
                ctx.path == "/v1/messages"
                and _is_openai_compat(fb_model)
                and not ctx.is_direct
            )
            candidates.append((fb_model, fb_url or UPSTREAM_URL, fb_key, fb_need_conv))

    client = await get_client()

    for attempt, (model, url, key, need_conv) in enumerate(candidates):
        if attempt > 0:
            prev = candidates[attempt - 1][0]
            logger.info("Fallback %d/%d: %s → %s", attempt, len(candidates) - 1, prev, model)

            ctx.resolved_model = model
            ctx.per_request_upstream_url = url
            ctx.per_request_upstream_api_key = key

            # Re-run protocol conversion when fallback uses a different protocol
            if need_conv != ctx.need_protocol_conv:
                ctx.need_protocol_conv = need_conv
                ctx.send_content = ctx.pre_conv_content or ctx.body
                if need_conv and ctx.send_content:
                    try:
                        oai = _anthropic_to_openai(json.loads(ctx.send_content.decode("utf-8")))
                        ctx.send_content = json.dumps(oai).encode("utf-8")
                    except Exception as exc:
                        logger.error("Fallback protocol re-conversion failed: %s — skipping %s", exc, model)
                        continue

            _build_target_url(ctx)

        # ── Per-attempt: refresh content-length and auth ──────────────────────
        if ctx.send_content is not None:
            ctx.headers["content-length"] = str(len(ctx.send_content))
        ctx.headers.pop("authorization", None)
        if ctx.per_request_upstream_api_key:
            ctx.headers["authorization"] = f"Bearer {ctx.per_request_upstream_api_key}"

        auth_present = "yes" if ctx.headers.get("authorization") else "no"
        model_label = f" model={ctx.resolved_model}" if ctx.resolved_model else ""
        logger.info(
            "Forwarding %s %s -> %s (auth=%s%s%s)",
            ctx.method, ctx.path, ctx.target_url, auth_present, model_label,
            f" attempt={attempt}" if attempt > 0 else "",
        )

        if ctx.send_content and ctx.content_type.startswith("application/json"):
            if logger.isEnabledFor(logging.DEBUG):
                try:
                    _dbg = json.loads(ctx.send_content)
                    if isinstance(_dbg, dict) and "messages" in _dbg:
                        struct = []
                        for m in _dbg["messages"]:
                            c = m.get("content")
                            if isinstance(c, list):
                                struct.append(
                                    f"{m.get('role')}:[{','.join(b.get('type', '?') for b in c if isinstance(b, dict))}]"
                                )
                            else:
                                struct.append(f"{m.get('role')}:str")
                        logger.debug("Msg structure: %s", " | ".join(struct))
                except Exception:
                    logger.exception("Debug message structure logging failed")

        try:
            upstream_resp = await client.send(
                client.build_request(
                    ctx.method, ctx.target_url, headers=ctx.headers, content=ctx.send_content
                ),
                stream=True,
            )
        except httpx.RequestError as exc:
            logger.error("Upstream request failed (attempt %d): %s", attempt, exc)
            if attempt < len(candidates) - 1:
                continue
            return JSONResponse({"error": "upstream request failed"}, status_code=502)

        # Retryable upstream error — try next fallback if available
        if upstream_resp.status_code in _RETRYABLE_STATUS and attempt < len(candidates) - 1:
            try:
                err_snippet = (await upstream_resp.aread()).decode("utf-8", errors="replace")[:200]
                logger.warning(
                    "Upstream %d on attempt %d (%s) — trying fallback: %s",
                    upstream_resp.status_code, attempt, model, err_snippet,
                )
            except Exception:
                pass
            finally:
                await upstream_resp.aclose()
            continue

        # ── Build response headers ────────────────────────────────────────────
        excluded_headers = {"content-encoding", "transfer-encoding", "content-length", "connection"}
        response_headers = {
            k: v for k, v in upstream_resp.headers.items() if k.lower() not in excluded_headers
        }
        if req_id:
            response_headers.setdefault("x-request-id", req_id)

        # Non-retryable upstream error (4xx, or retryable with no more fallbacks)
        if upstream_resp.status_code >= 400:
            try:
                err_body = await upstream_resp.aread()
                logger.error(
                    "Upstream %s error body: %s",
                    upstream_resp.status_code,
                    err_body.decode("utf-8", errors="replace")[:500],
                )
                return Response(
                    content=err_body,
                    status_code=upstream_resp.status_code,
                    headers=response_headers,
                )
            except Exception:
                logger.exception("Failed to read error body")
                return JSONResponse({"error": "upstream error"}, status_code=502)
            finally:
                await upstream_resp.aclose()

        # ── Protocol-converted response ───────────────────────────────────────
        if ctx.need_protocol_conv:
            is_stream = upstream_resp.headers.get("content-type", "").startswith("text/event-stream")
            if is_stream:
                async def converted_stream():
                    try:
                        async for chunk in _openai_stream_to_anthropic(
                            upstream_resp, ctx.resolved_model or ""
                        ):
                            yield chunk
                    except Exception as exc:
                        logger.error("Stream conversion error: %s", exc)
                    finally:
                        await upstream_resp.aclose()

                resp_headers = dict(response_headers)
                resp_headers["content-type"] = "text/event-stream; charset=utf-8"
                resp_headers["x-accel-buffering"] = "no"
                return StreamingResponse(converted_stream(), status_code=200, headers=resp_headers)
            else:
                try:
                    oai_body = await upstream_resp.aread()
                    await upstream_resp.aclose()
                    anthropic_resp = _openai_to_anthropic(json.loads(oai_body), ctx.resolved_model or "")
                    return JSONResponse(anthropic_resp, status_code=200)
                except Exception as exc:
                    logger.error("OpenAI→Anthropic conversion failed: %s", exc)
                    await upstream_resp.aclose()
                    return JSONResponse({"error": "response conversion failed"}, status_code=500)

        # ── Pass-through streaming ────────────────────────────────────────────
        async def async_iter_stream():
            try:
                async for chunk in upstream_resp.aiter_bytes():
                    yield chunk
            except Exception as exc:
                logger.error("Stream error: %s", exc)
            finally:
                await upstream_resp.aclose()

        if "text/event-stream" in upstream_resp.headers.get("content-type", ""):
            response_headers["x-accel-buffering"] = "no"

        return StreamingResponse(
            async_iter_stream(),
            status_code=upstream_resp.status_code,
            headers=response_headers,
        )

    return JSONResponse({"error": "all upstream attempts failed"}, status_code=502)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def forward_request(request: Request) -> Response:
    """Coordinate the full proxy pipeline for a single inbound request."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    content = await request.body()
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _DROP_HEADERS
    }

    if "x-request-id" not in headers:
        headers["x-request-id"] = str(uuid.uuid4())

    ctx = RequestContext(
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        headers=headers,
        body=content,
        content_type=request.headers.get("content-type", ""),
        per_request_upstream_url=UPSTREAM_URL,
        per_request_upstream_api_key=UPSTREAM_API_KEY,
        send_content=content,
    )

    from observability.stats import record
    _t_start = time.monotonic()

    _t_sanitize = time.monotonic()
    await _sanitize_and_route(ctx)
    _sanitize_ms = int((time.monotonic() - _t_sanitize) * 1000)

    await _maybe_convert_protocol(ctx)
    _build_target_url(ctx)

    _t_forward = time.monotonic()
    response = await _forward_to_upstream(ctx)
    _forward_ms = int((time.monotonic() - _t_forward) * 1000)

    _total_ms = int((time.monotonic() - _t_start) * 1000)
    status = getattr(response, "status_code", 0)
    logger.info(
        "req=%s total=%dms sanitize=%dms forward=%dms model=%s status=%d",
        headers["x-request-id"][:8], _total_ms, _sanitize_ms, _forward_ms,
        ctx.resolved_model or "unknown", status,
    )
    record(ctx.resolved_model or "unknown", status, _total_ms)
    return response

