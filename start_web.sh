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

# If patched Web Hub mode was requested, delegate to start_web_patched.sh
for arg in "$@"; do
    if [ "$arg" = "--patched" ] || [ "$arg" = "-P" ]; then
        if [ -f "$SCRIPT_DIR/start_web_patched.sh" ]; then
            exec "$SCRIPT_DIR/start_web_patched.sh" "${@/--patched/}"
        fi
    fi
done

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
RESTART=0
AUTO_OPEN=0
DIRECT_MODE=0
BROWSER_CMD=""
CUSTOM_BIN="${ANTIGRAVITY_LS_PATH:-${ANTIGRAVITY_FILE:-}}"
EDITOR_DIR="${ANTIGRAVITY_EDITOR_PATH:-${ANTIGRAVITY_EDITOR_DIR:-}}"

# Parse bash arguments
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    arg="${args[i]}"
    case "$arg" in
        --port|-p)
            if (( i + 1 < ${#args[@]} )); then
                PORT="${args[i+1]}"
                i=$((i+1))
            fi
            ;;
        --port=*)
            PORT="${arg#*=}"
            ;;
        --editor|-e)
            if (( i + 1 < ${#args[@]} )); then
                EDITOR_DIR="${args[i+1]}"
                i=$((i+1))
            fi
            ;;
        --editor=*)
            EDITOR_DIR="${arg#*=}"
            ;;
        --ls-path|-f|--file)
            if (( i + 1 < ${#args[@]} )); then
                CUSTOM_BIN="${args[i+1]}"
                i=$((i+1))
            fi
            ;;
        --ls-path=*)
            CUSTOM_BIN="${arg#*=}"
            ;;
        --kill-electron|-k)
            KILL_ELECTRON=1
            ;;
        --restart|-r)
            RESTART=1
            ;;
        --open|-o)
            AUTO_OPEN=1
            ;;
        --no-open)
            AUTO_OPEN=0
            ;;
        --direct|--no-proxy)
            DIRECT_MODE=1
            ;;
        --browser|-b)
            if (( i + 1 < ${#args[@]} )); then
                BROWSER_CMD="${args[i+1]}"
                i=$((i+1))
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
            echo "  -e, --editor PATH      Path to Antigravity editor root directory (e.g. /opt/Antigravity, /opt/Antigravity IDE)"
            echo "  -f, --ls-path PATH     Direct path to language_server binary or directory"
            echo "  -k, --kill-electron    Automatically terminate running Electron instances"
            echo "  -r, --restart          Force restart web server (terminate any running instance on port)"
            echo "  -o, --open             Automatically open web browser on startup"
            echo "      --direct           Bypass agy-proxy and connect directly to Google backend"
            echo "  -b, --browser NAME     Specify custom browser executable (e.g. helium, google-chrome)"
            echo "  -v, --verbose, --debug Show raw language_server console output (default: logged to file)"
            echo "  -h, --help             Show this help message"
            exit 0
            ;;
    esac
done

BIN=""

# Helper to find binary in an editor directory
find_in_editor_dir() {
    local ed="$1"
    [[ ! -d "$ed" ]] && return 1
    local subpaths=(
        "resources/bin"
        "resources/app/extensions/antigravity/bin"
        "Contents/Resources/bin"
        "Contents/Resources/app/resources/bin"
        "Contents/Resources/app/extensions/antigravity/bin"
        "Antigravity IDE/resources/app/extensions/antigravity/bin"
        "Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin"
        "Antigravity.app/Contents/Resources/bin"
        "bin"
        "."
    )
    local bnames=(
        "language_server"
        "language_server_linux_x64"
        "language_server_linux_arm"
        "language_server_linux_arm64"
        "language_server_macos_arm"
        "language_server_macos_x64"
        "language_server_darwin_arm64"
        "language_server_darwin_x64"
        "language_server_windows_x64.exe"
        "language_server.exe"
    )
    for sub in "${subpaths[@]}"; do
        local dir="${ed}/${sub}"
        if [[ -d "$dir" ]]; then
            for bn in "${bnames[@]}"; do
                if [[ -f "${dir}/${bn}" ]]; then
                    BIN="${dir}/${bn}"
                    return 0
                elif [[ -f "${dir}/${bn}.real" ]]; then
                    BIN="${dir}/${bn}.real"
                    return 0
                fi
            done
        fi
    done

    # Recursive fallback up to depth 6
    local found
    found=$(find "$ed" -maxdepth 6 -type f \( -name "language_server*" \) ! -name "*.log" ! -name "*.txt" ! -name "*.md" ! -name "*.py" ! -name "*.sh" ! -name "*.json" 2>/dev/null | head -n 1)
    if [[ -n "$found" && -f "$found" ]]; then
        BIN="$found"
        return 0
    fi
    return 1
}

# 1. Check explicit custom binary or editor dir
if [[ -n "$CUSTOM_BIN" ]]; then
    if [[ -f "$CUSTOM_BIN" ]]; then
        BIN="$CUSTOM_BIN"
    elif [[ -d "$CUSTOM_BIN" ]]; then
        find_in_editor_dir "$CUSTOM_BIN"
    fi
fi

# 2. Check explicit editor dir
if [[ -z "$BIN" && -n "$EDITOR_DIR" ]]; then
    find_in_editor_dir "$EDITOR_DIR"
fi

# 3. Check saved configuration file (~/.config/agy-proxy/config.json)
CONFIG_FILE="${HOME}/.config/agy-proxy/config.json"
if [[ -z "$BIN" && -f "$CONFIG_FILE" ]]; then
    cfg_ls=$(grep -o '"language_server_path"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" 2>/dev/null | sed -E 's/.*"language_server_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/' || true)
    if [[ -n "$cfg_ls" && -f "$cfg_ls" ]]; then
        BIN="$cfg_ls"
    fi
    if [[ -z "$BIN" ]]; then
        cfg_ed=$(grep -o '"editor_path"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" 2>/dev/null | sed -E 's/.*"editor_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/' || true)
        if [[ -n "$cfg_ed" && -d "$cfg_ed" ]]; then
            find_in_editor_dir "$cfg_ed"
        fi
    fi
fi

# 4. Detect from candidate system locations
if [[ -z "$BIN" ]]; then
    CANDIDATE_BINS=(
        # Linux Desktop App
        "/opt/Antigravity/resources/bin/language_server"
        "/opt/Antigravity/resources/bin/language_server.real"
        "/opt/antigravity/resources/bin/language_server"
        "${HOME}/.local/share/Antigravity/resources/bin/language_server"
        "${HOME}/.local/share/antigravity/resources/bin/language_server"
        "/usr/lib/antigravity/resources/bin/language_server"
        "${HOME}/Downloads/Antigravity app/Antigravity-x64/resources/bin/language_server"
        "${HOME}/Downloads/Antigravity app/Antigravity-arm64/resources/bin/language_server"
        # Linux Dedicated IDE
        "/opt/Antigravity IDE/resources/app/extensions/antigravity/bin/language_server_linux_x64"
        "/opt/Antigravity IDE/resources/app/extensions/antigravity/bin/language_server_linux_arm"
        "/opt/antigravity-ide/resources/app/extensions/antigravity/bin/language_server_linux_x64"
        "${HOME}/.local/share/Antigravity IDE/resources/app/extensions/antigravity/bin/language_server_linux_x64"
        "${HOME}/.local/share/Antigravity IDE/resources/app/extensions/antigravity/bin/language_server_linux_arm"
        "${HOME}/Downloads/Antigravity IDE/Antigravity IDE/resources/app/extensions/antigravity/bin/language_server_linux_arm"
        "${HOME}/Downloads/Antigravity IDE/resources/app/extensions/antigravity/bin/language_server_linux_x64"
        # macOS App & IDE
        "/Applications/Antigravity.app/Contents/Resources/bin/language_server"
        "/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin/language_server_macos_arm"
        "/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin/language_server_macos_x64"
        "${HOME}/Applications/Antigravity.app/Contents/Resources/bin/language_server"
        "${HOME}/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin/language_server_macos_arm"
        "${HOME}/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin/language_server_macos_x64"
    )

    for cand in "${CANDIDATE_BINS[@]}"; do
        if [ -f "$cand" ]; then
            BIN="$cand"
            break
        fi
    done
fi

# 5. PATH fallback
if [[ -z "$BIN" ]]; then
    for bn in "language_server" "language_server.exe"; do
        which_path=$(command -v "$bn" 2>/dev/null || true)
        if [[ -n "$which_path" && -f "$which_path" ]]; then
            BIN="$which_path"
            break
        fi
    done
fi

# 6. Interactive fallback if running in a terminal
if [[ -z "$BIN" && -t 0 ]]; then
    echo -e "\033[1;33m⚠️  Could not auto-detect Antigravity language_server path.\033[0m"
    echo "Antigravity may be installed in a custom location."
    read -r -e -p "Enter path to Antigravity directory or language_server binary: " user_path
    if [[ -n "$user_path" ]]; then
        user_path="${user_path/#\~/$HOME}"
        user_path="${user_path%\"}"
        user_path="${user_path#\"}"
        user_path="${user_path%\'}"
        user_path="${user_path#\'}"
        if [[ -f "$user_path" ]]; then
            BIN="$user_path"
        elif [[ -d "$user_path" ]]; then
            find_in_editor_dir "$user_path"
        fi
        if [[ -n "$BIN" ]]; then
            mkdir -p "$(dirname "$CONFIG_FILE")"
            if command -v python3 >/dev/null 2>&1; then
                python3 -c "import json, os; p='$CONFIG_FILE'; d=json.load(open(p)) if os.path.exists(p) else {}; d['language_server_path']='$BIN'; json.dump(d, open(p,'w'), indent=2)" 2>/dev/null || true
            fi
            echo -e "\033[1;32m✓ Saved language server binary to configuration:\033[0m $BIN"
        fi
    fi
fi

if [ -z "$BIN" ]; then
    echo -e "\033[0;31m❌ Error: Could not locate Antigravity language_server binary.\033[0m"
    echo "Please set ANTIGRAVITY_LS_PATH, specify via '-e /path/to/editor', or run:"
    echo "  agy-proxy config set ls-path /path/to/language_server"
    exit 1
fi

# Restart handling
if [ "$RESTART" -eq 1 ]; then
    echo -e "\033[1;33m🔄 Restart requested: terminating existing language_server instances...\033[0m"
    pkill -f "language_server.*--https_server_port.*$PORT" 2>/dev/null || true
    pkill -f "language_server.*--standalone" 2>/dev/null || true
    sleep 1
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

# Background browser open only if requested
if [ "$AUTO_OPEN" -eq 1 ]; then
    (
        sleep 2
        if [ -n "$BROWSER_CMD" ] && command -v "$BROWSER_CMD" >/dev/null 2>&1; then
            "$BROWSER_CMD" "${URL}" >/dev/null 2>&1 &
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "${URL}" >/dev/null 2>&1 &
        fi
    ) &
fi

FINAL_ARGS=(
    "--standalone"
    "--override_ide_name" "antigravity"
    "--subclient_type" "hub"
    "--override_ide_version" "2.24.0"
    "--override_user_agent_name" "antigravity"
    "--https_server_port" "$PORT"
    "--csrf_token" "$CSRF_TOKEN"
    "--app_data_dir" "antigravity"
    "--enable_sidecars"
)

# Check if agy-proxy is alive
DEFAULT_API_URL="https://generativelanguage.googleapis.com"
DEFAULT_CC_ENDPOINT="https://daily-cloudcode-pa.googleapis.com"

if [ "${DIRECT_MODE:-0}" -ne 1 ] && (curl -sf --max-time 1 "${PROXY_URL}/health" >/dev/null 2>&1 || curl -sf --max-time 1 "${PROXY_URL}/api/info" >/dev/null 2>&1); then
    FINAL_ARGS+=("--api_server_url" "$PROXY_URL" "--cloud_code_endpoint" "$PROXY_URL")
    echo -e "🔄 \033[1;32magy-proxy active at ${PROXY_URL}\033[0m -> routing AI traffic through proxy"
else
    FINAL_ARGS+=("--api_server_url" "$DEFAULT_API_URL" "--cloud_code_endpoint" "$DEFAULT_CC_ENDPOINT")
    if [ "${DIRECT_MODE:-0}" -eq 1 ]; then
        echo -e "🔄 \033[1;33mDirect Google Mode\033[0m -> proxy bypassed explicitly"
    else
        echo -e "🔄 \033[1;33mDirect Google Mode\033[0m -> proxy ${PROXY_URL} offline, falling back to official Google backend"
    fi
fi

LOG_FILE="${HOME}/.config/Antigravity/logs/language_server.log"
mkdir -p "$(dirname "$LOG_FILE")"

if [ "${VERBOSE:-0}" -eq 1 ]; then
    exec "$BIN" "${FINAL_ARGS[@]}"
else
    echo -e "📄 Server logs:     \033[0;36m${LOG_FILE}\033[0m"
    exec "$BIN" "${FINAL_ARGS[@]}" >> "$LOG_FILE" 2>&1
fi
