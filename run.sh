#!/usr/bin/env bash
set -euo pipefail

# Simple runner: tries Docker Compose first, then host Headroom + local proxy,
# otherwise runs the proxy only. Writes PIDs to .run/ for stop.sh to use.

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT_DIR"

env_exists=false
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  env_exists=true
fi

mkdir -p .run

has_cmd() { command -v "$1" >/dev/null 2>&1; }

PORT=${PORT:-8080}

echo "Starting opencode-proxy (port $PORT)."

if has_cmd docker && docker compose version >/dev/null 2>&1; then
  echo "Detected Docker Compose — launching stack with docker compose up"
  docker compose up --build -d
  echo "Docker Compose started. Use 'docker compose logs -f opencode-proxy' to view logs."
  exit 0
fi

if has_cmd headroom; then
  echo "Found Headroom CLI — starting proxy on port $PORT, Headroom on port 8787"
  nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" >> .run/proxy.log 2>&1 &
  echo $! > .run/proxy.pid
  echo "Proxy started (pid $(cat .run/proxy.pid))."
  # Headroom forwards all LLM calls to the local proxy
  ANTHROPIC_TARGET_API_URL="http://localhost:${PORT}" \
  ANTHROPIC_API_KEY="${OPENCODE_API_KEY:-}" \
  OPENAI_TARGET_API_URL="http://localhost:${PORT}/v1" \
  OPENAI_API_KEY="${OPENCODE_API_KEY:-}" \
  nohup headroom proxy --host 0.0.0.0 --port 8787 \
    --memory --code-aware \
    --intercept-tool-results \
    >> .run/headroom.log 2>&1 &
  echo $! > .run/headroom.pid
  echo "Headroom started (pid $(cat .run/headroom.pid))."
  echo ""
  echo "Point your client at: ANTHROPIC_BASE_URL=http://localhost:8787"
  exit 0
fi

echo "Docker Compose not found and Headroom CLI not available. Starting proxy only."
nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" >> .run/proxy.log 2>&1 &
echo $! > .run/proxy.pid
echo "Proxy started (pid $(cat .run/proxy.pid)). To stop, run ./stop.sh"
echo ""
echo "Point your client at: ANTHROPIC_BASE_URL=http://localhost:${PORT}"
