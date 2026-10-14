#!/usr/bin/env bash
# =============================================================================
# Antigravity Web Mode Launcher (Zero-Electron Overhead)
# Starts Antigravity in browser-based Web mode, saving ~1.6 GB+ RAM.
# =============================================================================

set -e

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
    TARGET="$(readlink "$SOURCE")"
    if [[ $TARGET == /* ]]; then
        SOURCE="$TARGET"
    else
        DIR="$(dirname "$SOURCE")"
        SOURCE="$DIR/$TARGET"
    fi
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Try running via Python agy-proxy CLI first for rich diagnostics and process management
if command -v uv >/dev/null 2>&1; then
    exec uv run python -m agy_proxy.cli web "$@"
elif command -v python3 >/dev/null 2>&1 && python3 -c "import agy_proxy" >/dev/null 2>&1; then
    exec python3 -m agy_proxy.cli web "$@"
fi

# Fallback: Pure Bash Standalone Launcher
PORT="${PORT:-44741}"
PROXY_PORT="${AGY_PROXY_PORT:-8000}"
PROXY_URL="${AGY_PROXY_URL:-http://127.0.0.1:${PROXY_PORT}}"
KILL_ELECTRON=0
NO_OPEN=0
BROWSER_CMD=""

# Parse bash arguments
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    arg="${args[i]}"
    case "$arg" in
        --port|-p)
            if (( i + 1 < ${#args[@]} )); then
                PORT="${args[i+1]}"
            fi
            ;;
        --port=*)
            PORT="${arg#*=}"
            ;;
        --kill-electron|-k)
            KILL_ELECTRON=1
            ;;
        --no-open)
            NO_OPEN=1
            ;;
        --browser|-b)
            if (( i + 1 < ${#args[@]} )); then
                BROWSER_CMD="${args[i+1]}"
            fi
            ;;
        --debug|--verbose|-v)
            VERBOSE=1
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -p, --port PORT        HTTPS port for Antigravity Web UI (default: 44741)"
            echo "  -k, --kill-electron    Automatically terminate running Electron instances"
            echo "      --no-open          Do not automatically open browser on startup"
            echo "  -b, --browser NAME     Specify custom browser executable (e.g. helium, google-chrome)"
            echo "  -v, --verbose, --debug Show raw language_server console output (default: logged to file)"
            echo "  -h, --help             Show this help message"
            exit 0
            ;;
    esac
done

# Detect binary
CANDIDATE_BINS=(
    "/opt/Antigravity/resources/bin/language_server"
    "/opt/Antigravity/resources/bin/language_server.real"
    "/opt/antigravity/resources/bin/language_server"
    "${HOME}/.local/share/Antigravity/resources/bin/language_server"
    "/usr/lib/antigravity/resources/bin/language_server"
    "/opt/Antigravity IDE/resources/app/extensions/antigravity/bin/language_server"
    "/Applications/Antigravity.app/Contents/Resources/bin/language_server"
)

BIN=""
for cand in "${CANDIDATE_BINS[@]}"; do
    if [ -f "$cand" ]; then
        BIN="$cand"
        break
    fi
done

if [ -z "$BIN" ]; then
    echo -e "\033[0;31m❌ Error: Could not locate Antigravity language_server binary.\033[0m"
    echo "Please set ANTIGRAVITY_LS_PATH or install Antigravity."
    exit 1
fi

# Electron instance handling
if pgrep -f "/opt/Antigravity/antigravity" >/dev/null 2>&1 || pgrep -f "antigravity-ide" >/dev/null 2>&1; then
    if [ "$KILL_ELECTRON" -eq 1 ]; then
        echo -e "\033[1;33m🧹 Stopping running Electron processes to free ~1.6 GB RAM...\033[0m"
        pkill -f "/opt/Antigravity/antigravity" 2>/dev/null || true
        pkill -f "antigravity-ide" 2>/dev/null || true
        sleep 1
    else
        echo -e "\033[1;33m⚠️  Notice: Electron Antigravity window detected.\033[0m"
        echo "   Tip: Close Electron or run '$0 -k' to free 1.6+ GB of RAM."
    fi
fi

# CSRF Token
CSRF_TOKEN=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "antigravity-web-token-$(date +%s)")
URL="https://127.0.0.1:${PORT}/"

echo "============================================================"
echo -e "\033[1;36m🚀 Google Antigravity Web Server (No-Electron Mode)\033[0m"
echo "============================================================"
echo -e "🌐 Web UI URL:       \033[1;32m${URL}\033[0m"
echo -e "💾 RAM Optimization: \033[1;32m~1.6 GB Memory Saved\033[0m"
echo -e "🔑 CSRF Token:       ${CSRF_TOKEN}"
echo -e "📦 Binary:           ${BIN}"
echo "------------------------------------------------------------"
echo -e "\033[0;33mℹ️  Note: Browser will prompt to accept self-signed local SSL certificate.\033[0m"
echo -e "\033[0;33m   (Click Advanced -> Proceed / Continue to 127.0.0.1)\033[0m"
echo "⏹️  Press Ctrl+C to stop server"
echo "============================================================"

# Background browser open
if [ "$NO_OPEN" -ne 1 ]; then
    (
        sleep 2
        if [ -n "$BROWSER_CMD" ] && command -v "$BROWSER_CMD" >/dev/null 2>&1; then
            "$BROWSER_CMD" "${URL}" >/dev/null 2>&1 &
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "${URL}" >/dev/null 2>&1 &
        fi
    ) &
fi

# Check if agy-proxy is alive
FINAL_ARGS=(
    "--standalone"
    "--override_ide_name" "antigravity"
    "--subclient_type" "hub"
    "--override_ide_version" "2.23.0"
    "--override_user_agent_name" "antigravity"
    "--https_server_port" "$PORT"
    "--csrf_token" "$CSRF_TOKEN"
    "--app_data_dir" "antigravity"
    "--enable_sidecars"
)

LOG_FILE="${HOME}/.config/Antigravity/logs/language_server.log"
mkdir -p "$(dirname "$LOG_FILE")"

if [ "${VERBOSE:-0}" -eq 1 ]; then
    exec "$BIN" "${FINAL_ARGS[@]}"
else
    echo -e "📄 Server logs:     \033[0;36m${LOG_FILE}\033[0m"
    exec "$BIN" "${FINAL_ARGS[@]}" >> "$LOG_FILE" 2>&1
fi
