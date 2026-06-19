#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT_DIR"

echo "Stopping opencode-proxy components..."

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "Stopping docker compose stack..."
  docker compose down
fi

if [ -f .run/proxy.pid ]; then
  pid=$(cat .run/proxy.pid)
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Killing proxy pid $pid"
    kill "$pid" || true
  fi
  rm -f .run/proxy.pid
fi

if [ -f .run/headroom.pid ]; then
  pid=$(cat .run/headroom.pid)
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Killing headroom pid $pid"
    kill "$pid" || true
  fi
  rm -f .run/headroom.pid
fi

echo "Stopped."
