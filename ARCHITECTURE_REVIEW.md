# Architecture Review — opencode-proxy

> **Status:** Complete. All 24 prioritised recommendations resolved as of 2026-06-19.
> **Current architecture:** see [README.md](README.md).

---

## What was fixed

| Area | Fix |
|---|---|
| Monolith (1,001-line `main.py`) | Split into 8 modules + `conversion/` sub-package |
| God function `forward_request()` | 4-stage pipeline + `RequestContext` dataclass |
| No tests | 100+ tests across 6 files (unit + integration + streaming) |
| Silent exception swallowing | All sites upgraded to `logger.exception(...)` |
| Per-request httpx client | Shared `client.py`; classifier reuses same client |
| No request size limit | 50 MB cap via `RequestSizeLimitMiddleware` |
| Docker security | Non-root user, HEALTHCHECK |
| Auth header leak (P0) | `ctx.headers.pop("authorization", None)` before forwarding |
| Streaming usage always 0 (P0) | `output_tokens` accumulated from final SSE chunk |
| Classifier URL fragility (P0) | `/v1` dedup matches `_build_target_url` logic |
| SSE error drops stream (P0) | `try/except` wraps `aiter_bytes`; `message_stop` always emitted |
| Classifier caching | `_clf_cache` dict (256 entries) + `@lru_cache` on keyword fallback |
| `STOP_REASON_MAP` duplicated | Centralised in `conversion/__init__.py` |
| Deprecated `on_event` | Replaced with `lifespan` context manager |
| No `X-Request-ID` | Generated if absent, propagated to response |
| No `X-Accel-Buffering` | Added to all SSE response headers |
| Lying `MODEL_MAP` type hint | `Dict[str, Union[str, Dict[str, str]]]` |
| `MODEL_MAP` in `.env` | Moved to `models.json` (readable, diffable, not a secret) |
| Duplicate API key names | `OPENCODE_API_KEY` is the single canonical name |
| No `pyproject.toml` | Added with `[project]` metadata and dev extras |
| No CI | `.github/workflows/ci.yml` added |
| No `TypedDict` | `types.py` with `MessageBlock` and `AnthropicPayload` |
| URL validation | `_is_safe_url()` validates `MODEL_MAP` entries (SSRF surface) |
| Headroom monkey-patch | Image pinned to digest; `assert` validates patch target at build time |
