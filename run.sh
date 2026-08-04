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



echo "Starting opencode-proxy (proxy internal port $PORT, exposed on 8787)."

if has_cmd docker && docker compose version >/dev/null 2>&1; then
  echo "Detected Docker Compose — launching stack with docker compose up"
  docker compose up --build -d
  echo "Docker Compose started. Use 'docker compose logs -f opencode-proxy' to view logs."
  exit 0
fi

echo "Docker Compose not found. Starting proxy only."
nohup uvicorn opencode_proxy.main:app --host 0.0.0.0 --port "$PORT" >> .run/proxy.log 2>&1 &
echo $! > .run/proxy.pid
echo "Proxy started (pid $(cat .run/proxy.pid)). To stop, run ./stop.sh"
echo ""
echo "Point your client at: ANTHROPIC_BASE_URL=http://localhost:${PORT}"
