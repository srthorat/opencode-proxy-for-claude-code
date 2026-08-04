#!/usr/bin/env bash
set -euo pipefail


echo "=== Starting opencode-proxy server on port 8080 ==="
exec uvicorn opencode_proxy.main:app --host 0.0.0.0 --port 8080 --loop asyncio --http h11
