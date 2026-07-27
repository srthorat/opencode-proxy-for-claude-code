import json
import logging
import time
import uuid

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .http_utils import check_auth
from .http_utils import get_client
from .config import (
    ENABLE_GRAPHIFY_CONTEXT,
    FREE_AUTO_MODELS,
    GO_API_KEY,
    MODEL_MAP,
    UPSTREAM_API_KEY,
    UPSTREAM_URL,
    _ANTHROPIC_COMPAT_MODELS,
    is_anthropic_compat,
)
from .context import RequestContext
from .conversion.request import _anthropic_to_openai
from .conversion.response import _openai_to_anthropic
from .conversion.streaming import _openai_stream_to_anthropic
from .distiller import distill_payload_messages
from .deduplicator import deduplicate_messages
from .graphify import load_graphify_summary


from .personas import get_gstack_workflow_summary
from .indexer import ensure_workspace_indexed
from .key_pool import groq_pool, ollama_pool, pool

from .memory_db import get_workspace_memory_summary
from .observer import observe_payload
from .orchestrator import orchestrate_payload
from .personas import get_default_best_persona
from .skills_matcher import match_and_get_skills_context





from .router import auto_select_model, get_fallbacks, map_claude_model_name, resolve_model_config
from .sanitization import _sanitize_messages, strip_thinking_from_system
from .guards import scan_and_redact_secrets
from .response_cache import get_cached_response, store_cached_response


logger = logging.getLogger("opencode-proxy")

# Headers dropped from inbound requests before forwarding upstream.
# anthropic-beta carries beta flags (e.g. interleaved-thinking-2025-05-14) that
# OpenCode does not support; anthropic-version is Anthropic-specific.
_DROP_HEADERS = {"host", "anthropic-beta", "anthropic-version"}
_STRIP_QS = {"beta", "betas"}
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_openai_compat(model_name: str, target_url: str = "") -> bool:
    """Return True when the model uses OpenAI /chat/completions format."""
    return not is_anthropic_compat(model_name, target_url)


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
            distill_payload_messages(payload)
            deduplicate_messages(payload["messages"])



        if "system" in payload:
            payload["system"] = strip_thinking_from_system(payload["system"])

        workspace_path = None
        if getattr(ctx, "headers", None):
            hdrs = ctx.headers
            if isinstance(hdrs, dict):
                workspace_path = hdrs.get("x-workspace-path") or hdrs.get("x-project-path") or hdrs.get("X-Workspace-Path")
            elif hasattr(hdrs, "get"):
                workspace_path = hdrs.get("x-workspace-path") or hdrs.get("x-project-path")

        # Smart Proxy Middle-Layer Orchestrator
        orchestrated_context = orchestrate_payload(payload, workspace_path=workspace_path)
        if orchestrated_context:
            if "system" in payload and isinstance(payload["system"], str):
                payload["system"] = payload["system"] + "\n\n" + orchestrated_context
            elif "system" in payload and isinstance(payload["system"], list):
                payload["system"].append({"type": "text", "text": orchestrated_context})
            else:
                payload["system"] = orchestrated_context



        # Strip extended-thinking / betas fields unsupported by OpenCode
        thinking_val = payload.pop("thinking", None)

        payload.pop("betas", None)

        if "max_tokens" in payload and isinstance(payload["max_tokens"], int) and payload["max_tokens"] > 4000:
            payload["max_tokens"] = 4000



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

                # Dynamic routing: 3 simplified tiers — free / free-global / go (all paid)
                if _model_lower in (
                    "auto",
                    "free",
                    "free-auto",
                    "free-all",
                    "free-global",
                    "free-global-auto",
                    "go",
                    "go-auto",
                    "go-all",
                    "go-all-auto",
                ):
                    ctx.is_auto_routed = True
                    messages = payload.get("messages", [])
                    _forced_tier = {
                        "free": "free",
                        "free-auto": "free",
                        "free-all": "free",
                        "free-global": "free-global",
                        "free-global-auto": "free-global",
                        "go": "go",
                        "go-auto": "go",
                        "go-all": "go",
                        "go-all-auto": "go",
                    }.get(_model_lower)
                    _has_tools = bool(payload.get("tools"))  # agent mode signal
                    incoming_model = await auto_select_model(messages, forced_tier=_forced_tier, has_tools=_has_tools)
                    payload["model"] = incoming_model

            # Normalize incoming model key to match keys in MODEL_MAP (e.g. gemma-4-31b-it -> free-global/google/gemma-4-31b-it)
            if not _model_lower.startswith("direct:") and incoming_model not in MODEL_MAP:
                for prefix in ("google/", "opencode-go/", "free-global/", "free-global/google/", "free-global/cohere/"):
                    candidate = f"{prefix}{incoming_model}"
                    if candidate in MODEL_MAP:
                        incoming_model = candidate
                        break

            upstream_model, upstream_url, upstream_api_key, role = resolve_model_config(incoming_model)
            ctx.is_direct = role == "direct"
            payload["model"] = upstream_model
            ctx.resolved_model = upstream_model
            ctx.config_model_key = incoming_model
            ctx.per_request_upstream_url = upstream_url or UPSTREAM_URL
            ctx.per_request_upstream_api_key = upstream_api_key if upstream_api_key is not None else UPSTREAM_API_KEY

            # Go-tier isolation: always use the dedicated go key for /zen/go/ requests.
            if GO_API_KEY and "/zen/go" in (ctx.per_request_upstream_url or ""):
                ctx.per_request_upstream_api_key = GO_API_KEY
            ctx.is_google = False

        ctx.send_content = json.dumps(payload).encode("utf-8")

    except Exception:
        logger.exception("Payload processing error (leaving body as-is)")


# ---------------------------------------------------------------------------
# Pipeline stage 2: Anthropic → OpenAI protocol conversion (if needed)
# ---------------------------------------------------------------------------


async def _maybe_convert_protocol(ctx: RequestContext) -> None:
    """Convert the Anthropic /v1/messages payload to OpenAI /chat/completions or Google GenAI format.

    Sets ctx.need_protocol_conv and rewrites ctx.send_content if conversion is needed.
    """


    ctx.need_protocol_conv = (
        ctx.path == "/v1/messages"
        and ctx.resolved_model is not None
        and _is_openai_compat(ctx.resolved_model, ctx.per_request_upstream_url or "")
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
            except Exception:
                logger.exception("Legacy completions path rewrite failed")
    elif path.startswith("/v1/chat/completions"):
        path = path.replace("/v1/chat/completions", "/chat/completions", 1)

    # If base already includes /v1 and path also starts with /v1, avoid duplication
    if base.endswith("/v1") and path.startswith("/v1"):
        path = path[len("/v1") :]

    target_url = base + path
    # Collapse accidental duplicate version segments like /v1/v1/ → /v1/
    target_url = target_url.replace("/v1/v1/", "/v1/")

    if ctx.query:
        qs_parts = [p for p in ctx.query.split("&") if p.split("=")[0].lower() not in _STRIP_QS]
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
    candidates: list[tuple[str, str, str | None, bool, str | None]] = [
        (
            ctx.resolved_model or "",
            ctx.per_request_upstream_url,
            ctx.per_request_upstream_api_key,
            ctx.need_protocol_conv,
            ctx.config_model_key,
        )
    ]
    lookup_key = ctx.config_model_key or ctx.resolved_model
    if lookup_key and ctx.is_auto_routed:
        for fb in get_fallbacks(lookup_key):
            fb_model, fb_url, fb_key, _ = resolve_model_config(fb)
            fb_need_conv = ctx.path == "/v1/messages" and _is_openai_compat(fb_model) and not ctx.is_direct
            candidates.append((fb_model, fb_url or UPSTREAM_URL, fb_key, fb_need_conv, fb))

    client = await get_client()

    for attempt, (model, url, key, need_conv, config_key) in enumerate(candidates):
        ctx.resolved_model = model
        ctx.config_model_key = config_key
        ctx.per_request_upstream_url = url
        ctx.per_request_upstream_api_key = key
        ctx.need_protocol_conv = need_conv
        ctx.is_google = False

        if attempt > 0:
            prev = candidates[attempt - 1][0]
            logger.info("Fallback %d/%d: %s → %s", attempt, len(candidates) - 1, prev, model)

        # Re-run protocol conversion if needed for fallback candidate
        if attempt > 0:
            if need_conv and ctx.pre_conv_content:
                try:
                    oai = _anthropic_to_openai(json.loads(ctx.pre_conv_content.decode("utf-8")))
                    ctx.send_content = json.dumps(oai).encode("utf-8")
                except Exception as exc:
                    logger.error("Fallback OpenAI protocol conversion failed: %s — skipping %s", exc, model)
                    continue
            else:
                ctx.send_content = ctx.pre_conv_content or ctx.body

        _build_target_url(ctx)



        _active_key = key
        _active_pool = None
        if "api.groq.com" in (ctx.per_request_upstream_url or "") and groq_pool.has_keys():
            _active_pool = groq_pool
        elif model in FREE_AUTO_MODELS and pool.has_keys():
            _active_pool = pool
        elif is_anthropic_compat(model, ctx.per_request_upstream_url or "") and ollama_pool.has_keys():
            _active_pool = ollama_pool


        if _active_pool:
            _pooled = _active_pool.get_key(model)
            if _pooled:
                _active_key = _pooled
            else:
                logger.warning("key-pool: all keys demoted for %s — using config key", model)

        # ── Inner key-rotation loop ────────────────────────────────────────────
        # Retries the same model with the next healthy key on 401/429.
        # Breaks out normally on success or non-key error; sets
        # _req_failed=True on network errors so the outer loop can continue.
        _req_failed = False
        upstream_resp = None
        while True:
            # Per-attempt: refresh content-length and auth
            if ctx.send_content is not None:
                ctx.headers["content-length"] = str(len(ctx.send_content))
            ctx.headers.pop("authorization", None)
            ctx.headers.pop("x-api-key", None)
            ctx.headers.pop("x-goog-api-key", None)
            ctx.headers.pop("anthropic-version", None)
            ctx.headers.pop("anthropic-beta", None)
            if _active_key and _active_key != "none":
                ctx.headers["authorization"] = f"Bearer {_active_key}"




            auth_present = "yes" if ctx.headers.get("authorization") else "no"
            model_label = f" model={ctx.resolved_model}" if ctx.resolved_model else ""
            logger.info(
                "Forwarding %s %s -> %s (auth=%s%s%s)",
                ctx.method,
                ctx.path,
                ctx.target_url,
                auth_present,
                model_label,
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
                assert ctx.target_url is not None
                t0 = time.time()
                upstream_resp = await client.send(
                    client.build_request(ctx.method, ctx.target_url, headers=ctx.headers, content=ctx.send_content),
                    stream=True,
                )

            except httpx.RequestError as exc:
                logger.error("Upstream request failed (attempt %d): %s", attempt, exc)
                _req_failed = True
                break  # exit key loop; outer loop handles continuation

            # ── Key rotation on error or latency benchmark on success ─────────────────
            if upstream_resp.status_code >= 400 and _active_pool:
                _active_pool.demote(_active_key, model)
                _next_key = _active_pool.get_key(model)
                if _next_key and _next_key != _active_key:
                    logger.warning(
                        "key-pool: key[%d] got %d for %s — rotating to key[%d]",
                        _active_pool._key_index(_active_key),
                        upstream_resp.status_code,
                        model,
                        _active_pool._key_index(_next_key),
                    )
                    await upstream_resp.aclose()
                    _active_key = _next_key
                    continue  # retry same model with next key
            elif upstream_resp.status_code == 200 and _active_pool:
                elapsed = time.time() - t0
                _active_pool.record_latency(model, elapsed)

            break  # success or unrecoverable — exit key loop



        # ── Handle network-level request failure ───────────────────────────────
        if _req_failed:
            if attempt < len(candidates) - 1:
                continue  # try next model candidate
            return JSONResponse({"error": "upstream request failed"}, status_code=502)

        # Retryable upstream error — try next fallback if available
        is_retryable = upstream_resp.status_code in _RETRYABLE_STATUS
        err_snippet = ""
        if not is_retryable and upstream_resp.status_code in (400, 401, 402, 403, 404) and attempt < len(candidates) - 1:
            try:
                body_bytes = await upstream_resp.aread()
                if (
                    b"ModelError" in body_bytes
                    or b"not supported" in body_bytes
                    or b"not found" in body_bytes
                    or b"CreditsError" in body_bytes
                    or b"GoUsageLimitError" in body_bytes
                    or b"payment method" in body_bytes
                    or b"billing" in body_bytes
                ):
                    is_retryable = True
                    err_snippet = body_bytes.decode("utf-8", errors="replace")[:200]
            except Exception:
                pass

        if is_retryable and attempt < len(candidates) - 1:
            try:
                if not err_snippet:
                    err_snippet = (await upstream_resp.aread()).decode("utf-8", errors="replace")[:200]
                logger.warning(
                    "Upstream %d on attempt %d (%s) — trying fallback: %s",
                    upstream_resp.status_code,
                    attempt,
                    model,
                    err_snippet,
                )
            except Exception:
                pass
            finally:
                await upstream_resp.aclose()
            continue

        # ── Build response headers ────────────────────────────────────────────
        excluded_headers = {"content-encoding", "transfer-encoding", "content-length", "connection"}
        response_headers = {k: v for k, v in upstream_resp.headers.items() if k.lower() not in excluded_headers}
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
        # ── Protocol-converted response ───────────────────────────────────────


        if ctx.need_protocol_conv:
            is_stream = upstream_resp.headers.get("content-type", "").startswith("text/event-stream")
            if is_stream:

                async def converted_stream():
                    try:
                        async for chunk in _openai_stream_to_anthropic(upstream_resp, ctx.resolved_model or ""):
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
                    resp_str, _ = scan_and_redact_secrets(json.dumps(anthropic_resp))
                    return JSONResponse(json.loads(resp_str), status_code=200)
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
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP_HEADERS}

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

    from .observability.stats import record

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
        headers["x-request-id"][:8],
        _total_ms,
        _sanitize_ms,
        _forward_ms,
        ctx.resolved_model or "unknown",
        status,
    )
    record(ctx.resolved_model or "unknown", status, _total_ms)
    return response
