# opencode-proxy (free-lite)

**Use Claude Code with [OpenCode](https://opencode.ai) free models — completely free, key pool rotation, and automatic context compression.**

This stack combines two tools:
- **opencode-proxy** — routes Claude Code requests to OpenCode free-tier, handles protocol translation, key pool rotation, and model selection.
- **[Headroom](https://headroom-docs.vercel.app)** — compresses your conversation history before each request, cutting token usage by 15–50%.

---

## Why does this exist?

[Claude Code](https://claude.ai/code) is a powerful AI coding assistant. By combining this proxy with OpenCode's free tier, you can run coding sessions completely free of charge. This proxy solves the key pain points of using the free tier:

### 1. Request Translation
Claude Code speaks the Anthropic format (`/v1/messages`). The proxy automatically translates requests to the OpenAI format (`/chat/completions`) expected by the OpenCode free models—including full streaming support for tool calls.

### 2. Multi-Key Pool Rotation
Free tiers have strict rate limits. The proxy supports automatic key-rotation using a pool of multiple API keys configured in your `.env`. If a key gets rate limited (429) or runs out of credits, the proxy immediately switches to the next healthy key and retries the request seamlessly.

### 3. Model Routing & Fallbacks
You can target a specific free model or use `"free-auto"` to let the proxy select the best model based on prompt complexity:
- **`big-pickle`** (Trivial tasks, one-liners)
- **`north-mini-code-free`** (Simple code, classifier tasks)
- **`deepseek-v4-flash-free`** (Fast general coding)
- **`mimo-v2.5-free`** (Flagship free general quality)

If a request to the auto-selected model fails on all keys, it gracefully falls back to the next model in the fallback chain.

### 4. Context Compression
Long coding sessions accumulate massive history. **[Headroom](https://headroom-docs.vercel.app)** compresses your context before each request—removing redundant tool results and old messages, saving massive amounts of token overhead.

---

## How it works

```
Claude Code
  │  ANTHROPIC_BASE_URL=http://localhost:8787
  ▼
Headroom :8787          ← compresses context
  │
  ▼
opencode-proxy :8080    ← routes model, converts protocol, rotates key pool
  │
  └─→ OpenCode zen/v1    (free models: big-pickle, north-mini-code-free, deepseek-v4-flash-free, mimo-v2.5-free)
```

---

## Quick Start

**1. Copy the environment template and fill in your OpenCode API keys:**

```bash
cp .env.example .env
# Edit .env — fill in OPENCODE_API_KEY, and optional rotation keys (OPENCODE_API_KEY_2, etc.)
```

**2. Start the Docker services:**

```bash
./run.sh
```

**3. Configure Claude Code to use the stack.** In `~/.claude/settings.json`:

```json
{
  "model": "free-auto",
  "availableModels": [
    "free-auto"
  ],
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8787",
    "ANTHROPIC_API_KEY": "placeholder-key"
  }
}
```

**4. Verify it's running:**

```bash
curl http://localhost:8080/healthz
# → {"status":"ok","upstream":"https://opencode.ai/zen/v1"}
```
