#!/usr/bin/env bash
set -euo pipefail

echo "=== Docker Auto-Boot: Verifying plugins and database prerequisites ==="
/app/scripts/setup.sh || true

echo "=== Starting opencode-proxy server on port 8080 ==="
exec uvicorn opencode_proxy.main:app --host 0.0.0.0 --port 8080 --loop asyncio --http h11
