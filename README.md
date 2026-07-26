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

---

## Graphify Integration

[Graphify](https://github.com/Graphify-Labs/graphify) builds a queryable, deterministic AST knowledge graph of codebases, SQL schemas, documentation, and config files without relying on vector stores.

### Quick Setup

1. **Setup the `/graphify` skill for Claude Code:**
   ```bash
   ./scripts/graphify_setup.sh
   ```

2. **Generate knowledge graph for your project:**
   Inside your workspace:
   ```text
   /graphify .
   ```

3. **Optional Proxy System-Prompt Injection:**
   If you prefer the proxy to automatically inject project graph topology into incoming requests:
   ```env
   ENABLE_GRAPHIFY_CONTEXT=true
   GRAPHIFY_GRAPH_PATH=graph.json
   ```

---

## Cross-Session Memory with claude-mem

[claude-mem](https://github.com/thedotmack/claude-mem) provides persistent cross-session memory for Claude Code using a local SQLite + FTS5 full-text search database.

### Setup

1. **Install the plugin for Claude Code:**
   ```bash
   ./scripts/claude_mem_setup.sh
   ```

2. **Start the optional Docker worker container:**
   ```bash
   docker-compose --profile with-claude-mem up -d
   ```

---

## Live Code Graph Mapping with claude-code-graph (ccg)

[aibozo/claude-code.graph](https://github.com/aibozo/claude-code.graph) (`ccg`) provides live, incremental AST dependency mapping using `tree-sitter`.

### Setup & Usage

1. **Install `claude-code-graph`:**
   ```bash
   ./scripts/claude_code_graph_setup.sh
   ```

2. **Launch session with live graph mapping:**
   ```bash
   ccg start
   ```

---

## Default Engineering Workflows with gstack

[garrytan/gstack](https://github.com/garrytan/gstack) provides opinionated engineering role skills (`/plan-ceo-review`, `/eng-review`, `/security-review`, `/qa-review`).

### Setup for Default Availability Across Any Repo

1. **Install `gstack` globally:**
   ```bash
   ./scripts/install_gstack.sh
   ```

---

---

## Official Anthropic Plugins (anthropics/claude-plugins-official)

[anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) provides Anthropic's official plugin marketplace.

### Setup for Backend Availability Across Any Repo

1. **Install official Anthropic plugins globally in backend:**
   ```bash
   ./scripts/install_official_plugins.sh
   ```

2. **One-Touch Full Stack Setup:**
   To install all global skills and plugins (`claude-plugins-official`, `gstack`, `anthropics/skills`, `graphify`, `claude-mem`) at once:
---

## 5 Proxy Super-Powers & Visual Web Dashboard

`opencode-proxy` includes 5 advanced capabilities out-of-the-box:

1. **AST Code Skeletonizer (`skeletonizer.py`)**: Converts large files into lightweight type/API skeletons (80% token reduction).
2. **Self-Healing Syntax Pre-Checker (`syntax_checker.py`)**: 1ms `ast.parse` syntax guard before file writes.
3. **0ms Response Cache (`response_cache.py`)**: Caches deterministic responses in `~/.opencode-proxy/cache.db` (0ms latency & 0 token cost).
4. **FTS5 Monorepo Linker (`monorepo_linker.py`)**: Cross-links symbol definitions across sibling repositories.
5. **Visual Web Dashboard (`http://localhost:8080/admin/dashboard`)**: Interactive dashboard showing real-time token savings, SmolLM2 speed, key health, and active workspace memory.







