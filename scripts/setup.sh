#!/usr/bin/env bash
# =============================================================================
# opencode-proxy unified setup
# Usage: ./scripts/setup.sh [plugin...]
#
# Examples:
#   ./scripts/setup.sh                 # full install (all plugins) — skips if already run
#   ./scripts/setup.sh --force         # force re-install everything
#   ./scripts/setup.sh gstack         # only gstack
#   ./scripts/setup.sh context7 sequential-thinking
#
# Available plugins: gstack, context7, sequential-thinking, superpowers,
#                    ui-ux-pro-max, anthropics-skills, official-plugins, services
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
CLAUDE_SKILLS_DIR="${CLAUDE_DIR}/skills"
PROXY_CACHE_DIR="${HOME}/.opencode-proxy/graphs"
SENTINEL_FILE="${HOME}/.opencode-proxy/.setup_complete"

mkdir -p "${CLAUDE_SKILLS_DIR}" "${PROXY_CACHE_DIR}"

# ── Sentinel: skip full install if already run (unless --force) ──────────────
FORCE=false
ARGS=()
for arg in "$@"; do
    if [ "${arg}" = "--force" ]; then FORCE=true; else ARGS+=("${arg}"); fi
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

if [ $# -eq 0 ] && [ -f "${SENTINEL_FILE}" ] && [ "${FORCE}" = "false" ]; then
    echo "opencode-proxy plugins already installed. Run with --force to reinstall."
    exit 0
fi

# ── Helpers ──────────────────────────────────────────────────────────────────

clone_or_pull() {
    local repo_url="$1" dest="$2"
    if [ -d "${dest}/.git" ]; then
        echo "  ↑ Updating $(basename "${dest}") …"
        git -C "${dest}" pull --ff-only --quiet || true
    else
        echo "  ↓ Cloning $(basename "${dest}") …"
        git clone --depth=1 --quiet "${repo_url}" "${dest}"
    fi
}

add_mcp_server() {
    local name="$1" cmd="$2"
    shift 2
    local args=("$@")
    if command -v claude &>/dev/null; then
        claude mcp add "${name}" "${cmd}" "${args[@]}" --scope global 2>/dev/null || true
    fi
}

ensure_claude_settings() {
    local settings="${CLAUDE_DIR}/settings.json"
    if [ ! -f "${settings}" ]; then
        echo "  Creating ~/.claude/settings.json …"
        cat > "${settings}" <<'JSON'
{
  "model": "groq-gpt-oss-120b",
  "availableModels": [
    "groq-gpt-oss-120b",
    "pollinations-openai",
    "pollinations-deepseek",
    "pollinations-openai-fast",
    "deepseek-v4-flash-free",
    "mimo-v2.5-free",
    "north-mini-code-free",
    "big-pickle",
    "qwen2.5-coder:32b",
    "free-auto"
  ],
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8787",
    "ANTHROPIC_API_KEY": "placeholder-key",

    "ENABLE_TOOL_SEARCH": "true"
  },
  "effortLevel": "medium"
}
JSON

    else
        echo "  ~/.claude/settings.json exists — ensure ANTHROPIC_BASE_URL=http://localhost:8787"
    fi
}

# ── Plugin installers ─────────────────────────────────────────────────────────

install_gstack() {
    echo "[gstack] Installing …"
    local dest="${CLAUDE_SKILLS_DIR}/gstack"
    clone_or_pull "https://github.com/gstack/gstack-claude-skill" "${dest}" 2>/dev/null \
        || mkdir -p "${dest}"
    add_mcp_server "gstack" "npx" "-y" "@gstack/mcp"
    echo "[gstack] Done."
}

install_context7() {
    echo "[context7] Installing …"
    add_mcp_server "context7" "npx" "-y" "@upstash/context7-mcp@latest"
    echo "[context7] Done."
}

install_sequential_thinking() {
    echo "[sequential-thinking] Installing …"
    add_mcp_server "sequential-thinking" "npx" "-y" "@modelcontextprotocol/server-sequential-thinking"
    echo "[sequential-thinking] Done."
}

install_superpowers() {
    echo "[superpowers] Installing …"
    local dest="${CLAUDE_SKILLS_DIR}/superpowers"
    clone_or_pull "https://github.com/obra/superpowers" "${dest}" 2>/dev/null \
        || mkdir -p "${dest}"
    echo "[superpowers] Done."
}

install_ui_ux_pro_max() {
    echo "[ui-ux-pro-max] Installing …"
    local dest="${CLAUDE_SKILLS_DIR}/ui-ux-pro-max"
    clone_or_pull "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill" "${dest}" 2>/dev/null \
        || mkdir -p "${dest}"
    echo "[ui-ux-pro-max] Done."
}

install_anthropics_skills() {
    echo "[anthropics-skills] Installing …"
    local dest="${CLAUDE_SKILLS_DIR}/anthropic-skills"
    clone_or_pull "https://github.com/anthropics/anthropic-cookbook" "${dest}" 2>/dev/null \
        || mkdir -p "${dest}"
    echo "[anthropics-skills] Done."
}

install_official_plugins() {
    echo "[official-plugins] Installing …"
    if command -v claude &>/dev/null; then
        claude plugin marketplace list 2>/dev/null | while read -r plugin; do
            claude plugin install "${plugin}" 2>/dev/null || true
        done
    fi
    echo "[official-plugins] Done."
}

install_services() {
    echo "[services] Setting up graphify, claude-mem, code-graph …"
    # graphify
    if command -v graphify &>/dev/null; then
        graphify install || true
    elif command -v npx &>/dev/null; then
        npx -y graphify install 2>/dev/null || true
    fi
    # claude-mem
    if command -v claude &>/dev/null; then
        claude plugin marketplace add thedotmack/claude-mem 2>/dev/null || true
        claude plugin install claude-mem 2>/dev/null || true
    fi
    echo "[services] Done."
}

install_all() {
    echo "=== opencode-proxy Full Setup: Installing ALL plugins ==="
    ensure_claude_settings
    install_gstack
    install_context7
    install_sequential_thinking
    install_superpowers
    install_ui_ux_pro_max
    install_anthropics_skills
    install_official_plugins
    install_services
    touch "${SENTINEL_FILE}"
    echo ""
    echo "=== All plugins installed. Run: docker compose up -d ==="
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

if [ $# -eq 0 ]; then
    install_all
    exit 0
fi

for plugin in "$@"; do
    case "${plugin}" in
        gstack)               install_gstack ;;
        context7)             install_context7 ;;
        sequential-thinking)  install_sequential_thinking ;;
        superpowers)          install_superpowers ;;
        ui-ux-pro-max)        install_ui_ux_pro_max ;;
        anthropics-skills)    install_anthropics_skills ;;
        official-plugins)     install_official_plugins ;;
        services)             install_services ;;
        all)                  install_all ;;
        *)
            echo "Unknown plugin: ${plugin}"
            echo "Available: gstack context7 sequential-thinking superpowers ui-ux-pro-max anthropics-skills official-plugins services all"
            exit 1
            ;;
    esac
done
