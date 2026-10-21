#!/usr/bin/env bash
# ==============================================================================
# Antigravity Patched Web Hub (Experimental Auto-Extractor & Runner)
# Starts Antigravity in browser-based Web mode with patched Web UI bundle.
# Delegated to Python agy-proxy CLI (agy_proxy/web_launcher.py)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    exec "$SCRIPT_DIR/.venv/bin/python" -m agy_proxy.cli web --patched "$@"
elif command -v uv >/dev/null 2>&1; then
    exec uv run python -m agy_proxy.cli web --patched "$@"
else
    exec python3 -m agy_proxy.cli web --patched "$@"
fi
