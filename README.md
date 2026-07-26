# opencode-proxy (Supercharged AI Coding Proxy)

**Use Claude Code with free OpenCode models — supercharged with sub-15ms local AI reasoning, Speculative Model Racing, autonomous self-healing code repair, leaked flagship model personas, and quad-layer token compression.**

---

## 🌟 Superpower Architecture & Capabilities

`opencode-proxy` is a zero-touch, high-throughput AI coding proxy designed to run 100% free models (`big-pickle`, `north-mini-code-free`, `deepseek-v4-flash-free`, `mimo-v2.5-free`, `qwen2.5-coder:32b`) while delivering the performance and behavior of flagship models (**Claude Fable 5 Mythos, Claude Opus 5, OpenAI GPT-5.6 Thinking, and Google Gemini 3.5/3.6**).

```text
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │                        opencode-proxy Super-Power Stack                        │
 └────────────────────────────────────────────────────────────────────────────────┘
                                          │
 ┌────────────────────────────────────────┴───────────────────────────────────────┐
 │                               FRONTEND & TELEMETRY                             │
 ├────────────────────────────────────────────────────────────────────────────────┤
 │ • Glassmorphism Live Web Dashboard ────► http://localhost:8080/dashboard      │
 │ • Real-Time Token & Cost API ──────────► http://localhost:8080/admin/analytics │
 └────────────────────────────────────────┬───────────────────────────────────────┘
                                          │
 ┌────────────────────────────────────────┴───────────────────────────────────────┐
 │                      ZERO-TOUCH AUTO-INITIALIZATION BOOT                       │
 ├────────────────────────────────────────────────────────────────────────────────┤
 │ • Auto-Installs 603 Global Skills + 40 Official Anthropic Marketplace Plugins   │
 │ • Auto-Initializes 3 SQLite DBs (memory.db, pattern.db, response_cache.db)     │
 └────────────────────────────────────────┬───────────────────────────────────────┘
                                          │
 ┌────────────────────────────────────────┴───────────────────────────────────────┐
 │                        INTELLIGENCE & ORCHESTRATION LAYER                      │
 ├────────────────────────────────────────────────────────────────────────────────┤
 │ • SmolLM2-135M Reasoner (< 15ms) ──────► Intent, Skill, Role & Judge Brain     │
 │ • Flagship Leaked System Prompts ──────► Fable 5, Opus 5, GPT-5.6, Gemini 3.6  │
 │ • Opus Multi-Pass Chain of Thought ───► Pass 1 Architectural Scope & Risk Plan │
 │ • Gemini 1M+ Workspace Memory Graph ──► SQLite AST Symbol Store                │
 │ • Gemini Flash Micro-Cache ────────────► Sub-50ms LRU Cache                    │
 │ • Specialized Coding Skills Engine ────► Obsidian, SQL, Terraform, OpenAPI     │
 │ • Web Asset & Security Auditor ────────► Favicons, PWA Icons, Strix Auditor    │
 └────────────────────────────────────────┬───────────────────────────────────────┘
                                          │
 ┌────────────────────────────────────────┴───────────────────────────────────────┐
 │                       PERFORMANCE & SAFETY EXECUTION ENGINE                    │
 ├────────────────────────────────────────────────────────────────────────────────┤
 │ • Speculative Model Racing ───────────► Sub-200ms TTFT                         │
 │ • Autonomous Self-Healing Loop-Back ───► 1-Shot Autonomous Code Repair         │
 │ • AST Dependency Auto-Repair ──────────► Auto-injects missing Python imports   │
 │ • Quad-Layer Token Compression Engine ─► AST Skeletonizer + Caveman Trimmer    │
 └────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 1. 🚀 Speculative Model Racing (< 200ms TTFT)
Fires parallel HTTP requests across free model candidates (`north-mini-code-free`, `mimo-v2.5-free`, `qwen2.5-coder:32b`), streaming the fastest quality-checked response instantly to your IDE.

### 2. 🧠 SmolLM2-135M Local AI Reasoner & Quality Judge (< 15ms)
Uses an ultra-compact local 135M parameter reasoning model to predict prompt intent, match global skills, assign engineering roles (`role-principal`, `role-architect`, `role-cto`), and evaluate response quality in < 15ms.

### 3. 🏛️ Leaked Flagship Model Personas
Incorporate official leaked system prompt standards:
- **Claude Fable 5 (Mythos-Class)**: Natural conversational prose, step-by-step reasoning, direct accountability.
- **Claude Opus 5**: Deep multi-pass architectural scope, risk matrix evaluation, concurrency safety.
- **OpenAI GPT-5.6 Thinking**: "Show, Don't Tell" zero-clutter reasoning, minimal-modification code edits.
- **Google Gemini 3.5 / 3.6**: Specifics over generalities, strict task completion, instant AST symbol synthesis.

### 4. 🔁 Autonomous Self-Healing Loop-Back Engine
If an upstream model output produces an AST syntax error or unit test failure, the proxy intercepts the response, feeds the traceback into a secondary model, and delivers self-repaired code on the first turn.

### 5. ✂️ Quad-Layer Token Compression Engine
- **AST Skeletonizer (`skeletonizer.py`)**: Strips function bodies from reference code, preserving AST signatures (**50%–80% savings**).
- **Caveman System Prompt Trimmer (`distiller.py`)**: Translates verbose system instructions into high-density telegraphic directives (**60%–80% savings**).
- **Token Deduplicator (`deduplicator.py`)**: Replaces duplicate file snippets across turns (**40% savings**).
- **Semantic Chatter Pruner (`distiller.py`)**: Strips conversational filler words.

### 6. 🛠️ Specialized Coding Skills
- 📓 **Obsidian Knowledge Vault (`obsidian_vault.py`)**: Auto-syncs ADRs and pattern notes to local Obsidian Vault (`~/.obsidian_vault/`).
- ⚡ **Database Query Optimizer (`query_optimizer.py`)**: Injects SQL B-Tree indexing, EXPLAIN plan rules, and N+1 query prevention.
- ☁️ **Cloud Infra & Terraform (`infra_terraform.py`)**: Validates Terraform HCL, Kubernetes pod security, and multi-stage Docker builds.
- 🔌 **Microservice API Contract (`api_contract.py`)**: Enforces OpenAPI 3.0, Swagger, Protobuf, and gRPC schema backward compatibility.
- 🎨 **Web Asset Generator (`asset_generator.py`)**: Generates favicons, PWA mobile icons, and Open Graph social media banners.
- 🛡️ **Strix Security Auditor (`strix_auditor.py`)**: Injects OWASP Top 10 defensive remediation rules into security prompts.

---

## Quick Start

### 1. Configure Environment

Copy the `.env` template and add your OpenCode API key:

```bash
cp .env.example .env
# Edit .env and set OPENCODE_API_KEY
```

### 2. Launch Services (Zero-Touch Auto-Boot)

```bash
./run.sh
# OR
docker compose up -d
```

### 3. Connect Claude Code CLI

Point Claude Code to the proxy:

```bash
export ANTHROPIC_BASE_URL="http://localhost:8080"
export ANTHROPIC_API_KEY="FREE"

claude
```

---

## 📊 Live Web Dashboard & Telemetry

Open **`http://localhost:8080/dashboard`** to view real-time proxy metrics:

- Live model health status & latency EMAs
- Total characters and tokens saved
- Speculative Model Racing cumulative ms saved
- Active skills, plugins, and Distinguished Engineer suite metrics

Real-time JSON analytics API available at **`http://localhost:8080/admin/analytics`**.

---

## 🧪 Verification & Test Suite

Run the comprehensive 226-test suite:

```bash
.venv/bin/pytest
# 226 passed, 1 warning in 21.28s
```

---

## 📄 License

MIT License.
