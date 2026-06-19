# opencode-proxy

**Use Claude Code with [OpenCode](https://opencode.ai) models — cheaper, smarter routing, and automatic context compression.**

---

## Why does this exist?

[Claude Code](https://claude.ai/code) is a powerful AI coding assistant, but using it with Anthropic directly gets expensive fast. [OpenCode](https://opencode.ai) offers the same models (and others) at much lower cost — but plugging Claude Code into OpenCode directly has several problems:

### Problem 1 — Claude Code only speaks Anthropic, OpenCode models speak two protocols

Claude Code sends requests in **Anthropic format** (`/v1/messages`). But many OpenCode models expect **OpenAI format** (`/chat/completions`). Without this proxy, those models simply don't work.

This proxy automatically translates the request format — including full streaming support for tool calls.

### Problem 2 — Free and paid models live at different URLs

OpenCode has two tiers:
- **Paid (go-tier):** `https://opencode.ai/zen/go/v1`
- **Free:** `https://opencode.ai/zen/v1`

Claude Code only knows one `ANTHROPIC_BASE_URL`. If you point it at the go-tier URL and try to use a free model, the request goes to the wrong endpoint and fails. You can't point Claude Code at both URLs simultaneously.

This proxy knows which models are free vs paid and routes each request to the correct URL automatically.

### Problem 3 — Free model names don't work in Claude Code settings

If you try setting `"model": "north-mini-code-free"` or `"model": "mimo-v2.5-free"` in your Claude Code `settings.json`, it won't work — Claude Code validates model names against Anthropic's list, or passes them through without the right routing context.

This proxy lets you use simple routing tokens instead:
- `"model": "free-auto"` → automatically picks the best free model for your task
- `"model": "go-auto"` → automatically picks the best paid model for your task
- `"model": "claude-haiku-4-5"` → auto-mapped to `free-auto` (haiku = cheap = free tier)
- Any other `claude-*` model → auto-mapped to `go-auto`

### Problem 4 — Context grows, costs balloon

Long coding sessions accumulate a huge context window. Every request re-sends the entire conversation history. Costs grow linearly with session length.

**Headroom** (the companion service in this stack) compresses your context before each request — removing redundant tool results, summarising old messages, and stripping content Claude Code doesn't need to re-read. In practice it removes 15–25% of tokens per request, which compounds significantly over a long session.

---

## How it works

```
Claude Code
  │  ANTHROPIC_BASE_URL=http://localhost:8787
  ▼
Headroom :8787          ← compresses context, strips redundant history
  │
  ▼
opencode-proxy :8080    ← routes model, converts protocol, handles fallbacks
  │
  ├─→ OpenCode zen/go/v1   (paid models: kimi, deepseek, qwen, minimax, mimo, glm)
  └─→ OpenCode zen/v1      (free models: big-pickle, north-mini-code-free, etc.)
```

Both services run in Docker on your laptop. Claude Code talks to Headroom on port 8787. Port 8080 is internal only.

---

## Quick start

**1. Get an OpenCode API key** at [opencode.ai](https://opencode.ai) (much cheaper than Anthropic directly).

**2. Configure and start:**

```bash
cp .env.example .env
# Edit .env — fill in your OPENCODE_API_KEY
./run.sh
```

**3. Point Claude Code at the stack.** In `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8787",
    "ANTHROPIC_API_KEY": "any-value"
  },
  "model": "go-auto"
}
```

That's it. Claude Code now routes through Headroom → proxy → OpenCode.

```bash
./stop.sh   # to shut everything down
```

---

## Choosing a model

Set `"model"` in `~/.claude/settings.json`:

| Setting | What happens | Cost |
|---|---|---|
| `go-auto` | Proxy picks the best paid model for each task | Paid |
| `free-auto` | Proxy picks the best free model for each task | Free |
| `claude-haiku-*` | Same as `free-auto` | Free |
| `claude-sonnet-*`, `claude-opus-*` | Same as `go-auto` | Paid |
| `kimi-k2.7`, `qwen3.7-max`, … | Pin to a specific model | Paid |

**How `go-auto` works:** Each request is classified by task type (code, reasoning, long context, creative, agent) and routed to the best-suited model. A coding question goes to `kimi-k2.7`, an architecture discussion goes to `deepseek-v4-pro`, a long document summary goes to `minimax-m3`.

**Fallback chains:** If a model returns an error (rate limit, timeout, 5xx), the proxy automatically retries with the next model in the chain — no interruption to your session.

---

## Configuration (`.env`)

| Variable | Required | Description |
|---|---|---|
| `OPENCODE_API_KEY` | ✅ | Your OpenCode API key |
| `UPSTREAM_URL` | ✅ | Paid endpoint: `https://opencode.ai/zen/go/v1` |
| `OPENCODE_FREE_URL` | ✅ for free models | Free endpoint: `https://opencode.ai/zen/v1` |
| `PORT` | — | Proxy listen port (default `8080`) |
| `PROXY_API_KEY` | — | Optional: require a Bearer token on inbound requests |
| `DIRECT_URL` / `DIRECT_KEY` | — | Optional: bypass OpenCode for `direct:<model>` requests |

Copy `.env.example` to `.env` to get started.

---

## Observability

```bash
# What's happening right now
curl http://localhost:8787/admin/stats | jq
# → total requests, by model, status codes, p50/p95/p99 latency

# How much context Headroom has compressed
curl http://localhost:8787/stats | jq
# → tokens removed, compression %, best single compression

# Per-request timing in Docker logs
docker compose logs opencode-proxy -f
# req=c9689b54 total=5374ms sanitize=5ms forward=5368ms model=minimax-m3 status=200
```

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v     # 140 tests, ~0.37s
ruff check .
mypy *.py conversion/
```

```
main.py          FastAPI app, health, /admin/stats
forward.py       4-stage pipeline: sanitize → route → convert → forward
router.py        Model classification and selection
sanitization.py  Message cleaner (strips thinking blocks, fixes tool results)
conversion/      Anthropic ↔ OpenAI protocol translation
models.json      Model routing config (URL, key, fallbacks per model)
```
