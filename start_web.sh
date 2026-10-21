#!/usr/bin/env bash
# =============================================================================
# Antigravity Web Mode Launcher (Zero-Electron Overhead)
# Starts Antigravity in browser-based Web mode, saving ~1.6 GB+ RAM.
# Delegated to Python agy-proxy CLI (agy_proxy/web_launcher.py)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    exec "$SCRIPT_DIR/.venv/bin/python" -m agy_proxy.cli web "$@"
elif command -v uv >/dev/null 2>&1; then
    exec uv run python -m agy_proxy.cli web "$@"
else
    exec python3 -m agy_proxy.cli web "$@"
fi
