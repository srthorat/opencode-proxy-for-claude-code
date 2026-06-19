# opencode-proxy

FastAPI proxy that routes **Claude Code** to [OpenCode](https://opencode.ai) instead of Anthropic. Handles model routing, message sanitisation, bidirectional Anthropic ↔ OpenAI protocol conversion, and streaming tool-call support.

```
Claude Code (ANTHROPIC_BASE_URL=http://localhost:8787)
    → Headroom :8787  (context compression)
    → opencode-proxy :8080  (internal)
    → OpenCode API (zen/go/v1 or zen/v1)
```

---

## Quick start

```bash
cp .env.example .env   # fill in OPENCODE_API_KEY
./run.sh               # starts Docker Compose stack
./stop.sh              # tears it down
```

In `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8787",
    "ANTHROPIC_API_KEY": "any-value"
  },
  "model": "go-auto"
}
```

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `OPENCODE_API_KEY` | ✅ | OpenCode bearer token |
| `UPSTREAM_URL` | ✅ | Go-tier endpoint (e.g. `https://opencode.ai/zen/go/v1`) |
| `OPENCODE_FREE_URL` | for free models | Free-tier endpoint |
| `PORT` | — | Proxy port (default `8080`) |
| `PROXY_API_KEY` | — | Require inbound `Authorization: Bearer <key>` |
| `DIRECT_URL` / `DIRECT_KEY` | — | Bypass OpenCode for `direct:<model>` requests |
| `MODEL_MAP` | — | JSON override for one-off model remapping (default: `models.json`) |

---

## Model routing

Use `"model"` in your Claude Code settings:

| Value | Behaviour |
|---|---|
| `go-auto` | LLM classifier picks best paid model per task |
| `free-auto` | LLM classifier picks best free model |
| `kimi-k2.7`, `qwen3.7-max`, … | Pin to a specific model |
| `direct:claude-opus-4-5` | Bypass OpenCode, forward to `DIRECT_URL` |
| `claude-haiku-*` | Auto-mapped to `free-auto` |
| `claude-*` (anything else) | Auto-mapped to `go-auto` |

**Agent mode** is auto-detected: when the payload includes a `tools` array and the conversation has ≥ 2 tool-use/result blocks, routing forces `mimo-v2.5-pro`.

### Go-tier categories

| Category | Model | When |
|---|---|---|
| `code` | `kimi-k2.7` | Algorithms, multi-file debug |
| `reasoning` | `deepseek-v4-pro` | Maths, architecture, analysis |
| `long` | `minimax-m3` | Large context, summarisation |
| `creative` | `qwen3.7-plus` | Writing, translation |
| `agent` | `mimo-v2.5-pro` | Agentic tool-use loops |
| `general` | `qwen3.7-max` | Everything else |

### Fallback chains

Each model in `models.json` declares `fallbacks`. On HTTP 429/5xx the proxy retries the next model automatically, re-converting the protocol if needed.

---

## Observability

```bash
# Per-request timing (in logs)
req=c9689b54 total=5374ms sanitize=1725ms forward=3648ms model=qwen3.7-max status=200

# In-memory stats (resets on restart)
curl http://localhost:8787/admin/stats | jq

# Headroom compression stats
curl http://localhost:8787/stats | jq
curl http://localhost:8787/metrics        # Prometheus format
```

---

## Production checklist

- [ ] Set `PROXY_API_KEY` (proxy warns on startup if unset)
- [ ] `chmod 600 .env`
- [ ] Rotate `OPENCODE_API_KEY` if it was ever in shell history or shared
- [ ] Port 8787 reachable only from trusted clients

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 140 tests, ~0.37s
ruff check .
mypy *.py conversion/
```

File layout:
```
main.py            FastAPI app, health, /admin/stats
forward.py         4-stage pipeline: sanitize → convert → forward → respond
router.py          Model classification and selection
sanitization.py    3-pass message cleaner
conversion/        Anthropic ↔ OpenAI (request, response, streaming)
observability/     In-memory stats
models.json        Model routing config (URL, key, fallbacks per model)
```
