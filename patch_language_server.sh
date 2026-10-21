#!/usr/bin/env bash
# =============================================================================
# Antigravity IDE -> Language Server Patcher & Manager
# Routes IDE backend requests through agy-proxy via wrapper script
# Delegated to Python agy-proxy CLI (agy_proxy/patcher.py)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    exec "$SCRIPT_DIR/.venv/bin/python" -m agy_proxy.cli patch "$@"
elif command -v uv >/dev/null 2>&1; then
    exec uv run python -m agy_proxy.cli patch "$@"
else
    exec python3 -m agy_proxy.cli patch "$@"
fi
