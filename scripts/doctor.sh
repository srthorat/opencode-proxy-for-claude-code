#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN=".venv/bin/python"
if [ ! -f "${PYTHON_BIN}" ]; then
    PYTHON_BIN="python3"
fi

"${PYTHON_BIN}" -m opencode_proxy.doctor
