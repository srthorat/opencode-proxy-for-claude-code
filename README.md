# opencode-proxy

A lightweight FastAPI proxy that lets **Claude Code** talk to [OpenCode](https://opencode.ai) instead of Anthropic directly. Handles automatic model routing, conversation sanitisation, bidirectional protocol conversion (Anthropic ↔ OpenAI), and full streaming tool-call support.

---

## Architecture

### Docker services

```
Claude Code (VS Code / CLI)
        │  ANTHROPIC_BASE_URL=http://localhost:8787
        ▼
┌────────────────────────────────────┐  Docker network
│  headroom  :8787                   │──────────────────┐
│  (context compression + memory)    │                  │
└────────────────────────────────────┘                  │
                                                        ▼
                                        ┌───────────────────────────┐
                                        │  opencode-proxy  :8080    │
                                        │  (internal only)          │
                                        │                           │
                                        │  ① auth gate              │
                                        │  ② sanitise messages      │
                                        │  ③ route → model          │
                                        │  ④ convert protocol       │
                                        │  ⑤ forward upstream       │
                                        └─────────────┬─────────────┘
                                                      │
                                                      ▼
                                        ┌─────────────────────────┐
                                        │  OpenCode API           │
                                        │  zen/go/v1  (paid)      │
                                        │  zen/v1     (free)      │
                                        └─────────────────────────┘
```

**opencode-proxy** is internal-only (port 8080 not exposed to host). **Headroom** is the public entry point (port 8787) — it compresses context before forwarding to the proxy.

### Code layout

```
main.py          Routes + lifespan + count_tokens estimate
forward.py       4-stage pipeline (sanitize/route → convert → forward)
router.py        Model selection (LLM classify + keyword fallback + map)
sanitization.py  3-pass message cleaner
auth.py          Timing-safe Bearer check
client.py        Shared httpx.AsyncClient lifecycle
config.py        Env-var loading + tier model maps
context.py       RequestContext dataclass
models.json      Model routing config (URL + key + fallbacks per model)
conversion/
  __init__.py    STOP_REASON_MAP
  request.py     Anthropic → OpenAI
  response.py    OpenAI → Anthropic (non-streaming)
  streaming.py   OpenAI → Anthropic (SSE)
observability/
  tracing.py     LangFuse request tracing (no-op when disabled)
tests/           100+ tests across 6 files
```

### Request pipeline

```
Inbound request
  │
  ├─ ① Auth check (PROXY_API_KEY if set)
  ├─ ② Sanitise: strip thinking blocks, fix orphaned tool_results, hoist system msgs
  ├─ ③ Route: claude-* → auto token → LLM classify → pick model from tier map
  ├─ ④ Convert: Anthropic /v1/messages → OpenAI /chat/completions (if needed)
  ├─ ⑤ Forward to upstream via shared httpx client (retries fallback models on 429/5xx)
  ├─ ⑥ Convert response back → Anthropic format (streaming + non-streaming)
  └─ ⑦ Trace: record model, status, fallbacks, latency to LangFuse (if enabled)
```

---

## Quick start

### 1. Configure `.env`

```env
OPENCODE_API_KEY=sk-...                          # your OpenCode key
UPSTREAM_URL=https://opencode.ai/zen/go/v1       # go-tier endpoint
OPENCODE_FREE_URL=https://opencode.ai/zen/v1     # free-tier endpoint
PORT=8080

# Optional
# PROXY_API_KEY=any-secret     # require inbound Bearer token
# DIRECT_URL=https://api.anthropic.com
# DIRECT_KEY=sk-ant-...
```

Copy `.env.example` as a starting point.

### 2. Start

```bash
./run.sh      # detects Docker Compose → falls back to host Headroom → standalone
./stop.sh     # tears everything down
```

Or directly:

```bash
docker compose up --build -d
docker compose logs -f
```

### 3. Configure Claude Code

In `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8787",
    "ANTHROPIC_API_KEY":  "any-value"
  },
  "model": "go-auto"
}
```

> Point at **port 8787** (Headroom) not 8080 (proxy is internal-only).

---

## Model routing

### Auto modes

| `model` value | Tier | Behaviour |
|---|---|---|
| `go-auto` | paid | LLM classifier → best paid model per task |
| `free-auto` | free | LLM classifier → best free model per task |
| `auto` | auto-detect | Detects tier AND category (prefer `go-auto`) |

**Agent mode** is detected automatically: when the payload includes a `tools` array and the conversation has ≥ 2 `tool_use`/`tool_result` blocks, routing is forced to the agent model regardless of query content.

### Go-tier auto-routing (category → model)

When using `go-auto`, the classifier picks from this map:

| Category | Model ID | Chosen when… |
|---|---|---|
| `code` | `kimi-k2.7` | Algorithms, multi-file debug, data structures |
| `reasoning` | `deepseek-v4-pro` | Architecture, maths, step-by-step analysis |
| `long` | `minimax-m3` | Large context, documents, summarisation |
| `creative` | `qwen3.7-plus` | Writing, translation, creative tasks |
| `agent` | `mimo-v2.5-pro` | Agentic loops with tool-use (auto-detected) |
| `fast` | `deepseek-v4-flash` | Quick go-tier tasks |
| `general` | `qwen3.7-max` | Everything else |

### All go-tier models (for direct use)

Pin any of these via `{ "model": "<model-id>" }`. The proxy routes to the correct endpoint automatically.

| Model name | Model ID | Endpoint | Notes |
|---|---|---|---|
| GLM-5.2 | `glm-5.2` | `/chat/completions` | |
| GLM-5.1 | `glm-5.1` | `/chat/completions` | alt GLM |
| Kimi K2.7 | `kimi-k2.7` | `/chat/completions` | best for code |
| Kimi K2.6 | `kimi-k2.6` | `/chat/completions` | alt Kimi |
| DeepSeek V4 Pro | `deepseek-v4-pro` | `/chat/completions` | best for reasoning |
| DeepSeek V4 Flash | `deepseek-v4-flash` | `/chat/completions` | fast go-tier |
| MiMo-V2.5 | `mimo-v2.5` | `/chat/completions` | general OAI |
| MiMo-V2.5-Pro | `mimo-v2.5-pro` | `/chat/completions` | best for agent/tool-use |
| MiniMax M3 | `minimax-m3` | `/messages` | best for long context |
| MiniMax M2.7 | `minimax-m2.7` | `/messages` | alt long context |
| MiniMax M2.5 | `minimax-m2.5` | `/messages` | alt long context |
| Qwen3.7 Max | `qwen3.7-max` | `/messages` | general quality default |
| Qwen3.7 Plus | `qwen3.7-plus` | `/messages` | best for creative |
| Qwen3.6 Plus | `qwen3.6-plus` | `/messages` | alt Qwen |

All models use base URL `https://opencode.ai/zen/go/v1` — `/chat/completions` models use OpenAI format, `/messages` models use Anthropic format.

### Free-tier model map

| Category | Model |
|---|---|
| `trivial` | `big-pickle` |
| `simple` | `north-mini-code-free` |
| `fast` | `deepseek-v4-flash-free` |
| `general` | `mimo-v2.5-free` |

### Named model

Pin to any specific model:
```json
{ "model": "minimax-m3" }
```

### Direct provider bypass

Bypass OpenCode entirely — send the request to any provider:
```env
DIRECT_URL=https://api.anthropic.com
DIRECT_KEY=sk-ant-...
```
```json
{ "model": "direct:claude-opus-4-5" }
```
The `direct:` prefix is stripped before forwarding. No protocol conversion — request goes through as-is.

### `claude-*` pass-through

If Claude Code sends a `claude-*` model name not in `models.json`, the proxy redirects it:

| Model name contains | Redirected to |
|---|---|
| `haiku` | `free-auto` |
| anything else `claude-*` | `go-auto` |

### Custom model remapping (`models.json`)

Edit `models.json` to add or override model routing. The `MODEL_MAP` env var overrides the file at runtime (useful for one-off testing):

```json
{
  "my-alias": "qwen3.7-max",
  "my-model": {
    "url":     "env:UPSTREAM_URL",
    "api_key": "env:OPENCODE_API_KEY",
    "role":    "go_coders/general"
  }
}
```

Use `"env:VAR_NAME"` to read URLs or keys from environment at runtime. URLs must start with `http://` or `https://`.

---

## Fallback chains

Each model in `models.json` has an optional `fallbacks` list. When the upstream returns a retryable error (HTTP 429, 500, 502, 503, 504), the proxy automatically retries the next model in the chain — no client-side change needed.

```json
"kimi-k2.7": {
  "role": "go_coders/code",
  "fallbacks": ["deepseek-v4-flash", "deepseek-v4-pro"]
}
```

If the primary and fallback models use different protocols (e.g., primary is OpenAI format, fallback is Anthropic format), the payload is automatically re-converted before the retry.

---

## Protocol conversion

Models fall into two groups — handled transparently by the proxy:

| Protocol | Endpoint | Models |
|---|---|---|
| Anthropic `/v1/messages` | `zen/go/v1/messages` | `minimax-m3`, `minimax-m2.7`, `minimax-m2.5`, `qwen3.7-max`, `qwen3.7-plus`, `qwen3.6-plus` |
| OpenAI `/chat/completions` | `zen/go/v1/chat/completions` | `kimi-k2.7`, `kimi-k2.6`, `deepseek-v4-pro`, `deepseek-v4-flash`, `mimo-v2.5`, `mimo-v2.5-pro`, `glm-5.2`, `glm-5.1` |
| OpenAI `/chat/completions` | `zen/v1/chat/completions` | `big-pickle`, `north-mini-code-free`, `deepseek-v4-flash-free`, `mimo-v2.5-free` |

Streaming tool calls are fully supported — each `tool_calls` delta is converted to the correct Anthropic SSE sequence (`content_block_start → content_block_delta → content_block_stop`).

---

## Conversation sanitisation

Three-pass sanitiser runs before every upstream request:

| Pass | What it does |
|---|---|
| 1 | Hoists inline `role: system` messages into the top-level `system` field |
| 2 | Recursively strips `redacted_thinking` and `thinking` blocks (including those nested inside `tool_result`) |
| 3 | Converts orphaned `tool_result` blocks (no matching prior `tool_use`) to plain text |

Also strips `thinking`, `betas`, `anthropic-beta`, and `anthropic-version` from every request.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OPENCODE_API_KEY` | — | Bearer token for OpenCode upstream (required) |
| `UPSTREAM_URL` | `https://api.opencode.ai` | OpenCode go-tier endpoint |
| `OPENCODE_FREE_URL` | — | OpenCode free-tier endpoint (required for free-tier models) |
| `PORT` | `8080` | Port the proxy listens on |
| `PROXY_API_KEY` | — | If set, all inbound requests must send `Authorization: Bearer <key>` |
| `DIRECT_URL` | — | Provider URL for `direct:<model>` mode |
| `DIRECT_KEY` | — | API key for `DIRECT_URL` |

---

## Observability

### Request stats

```
GET http://localhost:8787/admin/stats
→ {"uptime_seconds":3600,"total_requests":42,"by_model":{"kimi-k2.7":30,...},"by_status":{"2xx":40,"5xx":2},"p50_latency_ms":2100,"p95_latency_ms":5400,"p99_latency_ms":8900}
```

In-memory only — resets on restart. Gated behind `PROXY_API_KEY` if set.

### Per-request timing log

Every request emits one structured log line:

```
req=c9689b54 total=5374ms sanitize=1725ms forward=3648ms model=qwen3.7-max status=200
```

### Headroom compression stats

```
GET http://localhost:8787/stats    → compression savings, tokens removed
GET http://localhost:8787/metrics  → Prometheus counters
GET http://localhost:8787/health   → upstream connectivity, concurrency
```

---

## Production deployment checklist

- [ ] Set `PROXY_API_KEY` — proxy warns on startup if unset; without it any client can use your OpenCode key
- [ ] `chmod 600 .env` — restrict file permissions so only the owner can read the key
- [ ] Rotate `OPENCODE_API_KEY` if it was ever exposed (logs, shell history, shared machine)
- [ ] Set `LANGFUSE_ENABLED=false` (default) unless you have a reason to trace — it's an extra dependency and latency
- [ ] Pin Docker image tags in `docker-compose.yml` for reproducible deployments
- [ ] Run behind a firewall — port 8787 (Headroom) should only be reachable from trusted clients

---

## Health check

```
GET http://localhost:8787/healthz
→ {"status":"ok","upstream":"https://opencode.ai/zen/go/v1"}
```

---

## Development

```bash
make install     # pip install -e ".[dev]"
make test        # pytest tests/ -v
make lint        # ruff check .
make typecheck   # mypy *.py conversion/
make run         # uvicorn with --reload (no Docker)
```
