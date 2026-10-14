#!/usr/bin/env bash
# =============================================================================
# Antigravity IDE -> Language Server Patcher & Manager
# Routes IDE backend requests through agy-proxy via wrapper script
# =============================================================================

set -e

# Terminal Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Default settings
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
CUSTOM_URL="${AGY_PROXY_URL:-}"
WAIT_TIMEOUT="${AGY_PROXY_WAIT:-2}"
ENABLE_WATCHDOG="${AGY_PROXY_WATCHDOG:-1}"
CUSTOM_TARGET="${ANTIGRAVITY_LS_PATH:-${ANTIGRAVITY_FILE:-${ANTIGRAVITY_BIN_DIR:-${ANTIGRAVITY_EDITOR_PATH:-${ANTIGRAVITY_EDITOR_DIR:-}}}}}"
AUTO_CONFIRM=false
COMMAND=""

# Known candidate directories for Antigravity 2.0 and Antigravity IDE (Standalone)
CANDIDATE_DIRS=(
    # Google Antigravity 2.0 (Hub / Desktop App - Linux)
    "/opt/Antigravity/resources/bin"
    "/opt/Antigravity"
    "/opt/antigravity/resources/bin"
    "/opt/antigravity"
    "${HOME}/.local/share/Antigravity/resources/bin"
    "${HOME}/.local/share/Antigravity"
    "${HOME}/.local/share/antigravity/resources/bin"
    "${HOME}/.local/share/antigravity"
    "/usr/lib/antigravity/resources/bin"
    "/usr/lib/antigravity"
    "/usr/share/antigravity"

    # Google Antigravity IDE (Standalone Dedicated Editor - Linux)
    "/opt/Antigravity IDE/resources/app/extensions/antigravity/bin"
    "/opt/Antigravity IDE"
    "/opt/antigravity-ide/resources/app/extensions/antigravity/bin"
    "/opt/antigravity-ide"
    "${HOME}/.local/share/Antigravity IDE/resources/app/extensions/antigravity/bin"
    "${HOME}/.local/share/Antigravity IDE"
    "${HOME}/Downloads/Antigravity IDE/Antigravity IDE/resources/app/extensions/antigravity/bin"
    "${HOME}/Downloads/Antigravity IDE/Antigravity IDE"
    "${HOME}/Downloads/Antigravity IDE"
    "${HOME}/Downloads/Antigravity app"

    # macOS (Hub / Desktop App)
    "/Applications/Antigravity.app/Contents/Resources/bin"
    "/Applications/Antigravity.app/Contents/Resources/app/resources/bin"
    "/Applications/Antigravity.app"
    "${HOME}/Applications/Antigravity.app/Contents/Resources/bin"
    "${HOME}/Applications/Antigravity.app"

    # macOS (Dedicated Antigravity IDE)
    "/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin"
    "/Applications/Antigravity IDE.app"
    "${HOME}/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin"
    "${HOME}/Applications/Antigravity IDE.app"

    # Windows (WSL / Git-Bash)
    "/c/Users/${USER}/AppData/Local/Programs/Antigravity/resources/bin"
    "/mnt/c/Users/${USER}/AppData/Local/Programs/Antigravity/resources/bin"
    "/c/Users/${USER}/AppData/Local/Programs/Antigravity IDE/resources/app/extensions/antigravity/bin"
    "/mnt/c/Users/${USER}/AppData/Local/Programs/Antigravity IDE/resources/app/extensions/antigravity/bin"
)

KNOWN_BIN_NAMES=(
    # Universal / Desktop App (Linux & macOS)
    "language_server"
    # Windows Desktop App
    "language_server.exe"
    # Linux Dedicated IDE (x64, arm / arm64)
    "language_server_linux_x64"
    "language_server_linux_arm"
    "language_server_linux_arm64"
    # macOS Dedicated IDE (Apple Silicon & Intel)
    "language_server_macos_arm"
    "language_server_macos_x64"
    "language_server_darwin_arm64"
    "language_server_darwin_x64"
    # Windows Dedicated IDE (x64 & arm)
    "language_server_windows_x64.exe"
    "language_server_windows_arm.exe"
)

# Known relative subpaths within editor installation root
KNOWN_SUBPATHS=(
    "resources/bin"
    "resources/app/extensions/antigravity/bin"
    "resources/app/resources/bin"
    "Contents/Resources/bin"
    "Contents/Resources/app/resources/bin"
    "Contents/Resources/app/extensions/antigravity/bin"
    "Antigravity IDE/resources/app/extensions/antigravity/bin"
    "Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin"
    "Antigravity.app/Contents/Resources/bin"
    "bin"
)

# Print Help
show_help() {
    echo -e "${BOLD}Usage:${NC} $0 [COMMAND] [OPTIONS] [PATH_OR_DIR]"
    echo ""
    echo -e "${BOLD}Commands:${NC}"
    echo -e "  ${CYAN}patch${NC}             Install wrapper script to route language_server through agy-proxy"
    echo -e "  ${CYAN}restore${NC}           Restore original language_server binary (unpatch)"
    echo -e "  ${CYAN}status${NC}            Display current patching and process status"
    echo -e "  ${CYAN}restart${NC}           Restart running language_server so Antigravity respawns it"
    echo ""
    echo -e "${BOLD}Path Specification:${NC}"
    echo -e "  ${CYAN}-e, --editor PATH${NC}       Path to editor installation root (e.g. /opt/Antigravity, /opt/Antigravity IDE)"
    echo -e "  ${CYAN}-f, --file, --path PATH${NC} Direct path to language_server file or editor directory"
    echo -e "  ${CYAN}--dir PATH${NC}              Directory containing language_server or editor root"
    echo -e "  Or pass path directly as argument (e.g. $0 patch /opt/Antigravity or $0 status \"/opt/Antigravity IDE\")"
    echo ""
    echo -e "${BOLD}Options:${NC}"
    echo -e "  --port PORT         Port where agy-proxy is running (default: 8000 or \$PORT)"
    echo -e "  --host HOST         Host where agy-proxy is running (default: 127.0.0.1 or \$HOST)"
    echo -e "  --url URL           Full proxy URL (e.g. http://127.0.0.1:8000 or https://proxy.mydomain.com)"
    echo -e "  --timeout SECONDS   Max seconds to wait for agy-proxy at startup (default: 2, 0 to disable)"
    echo -e "  --no-wait           Disable waiting for agy-proxy before launching"
    echo -e "  --no-watchdog       Disable background watchdog for dynamic live switching"
    echo -e "  -y, --yes           Automatically answer yes to all confirmation prompts"
    echo -e "  -h, --help          Show this help message"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo -e "  $0 status                                                    # Check auto-detected status"
    echo -e "  $0 status -e /opt/Antigravity                                # Auto-detects within editor directory"
    echo -e "  $0 patch -e \"/opt/Antigravity IDE\"                           # Patch Antigravity IDE by editor root"
    echo -e "  $0 patch -f /opt/Antigravity/resources/bin/language_server   # Patch specific binary directly"
    echo -e "  $0 patch /opt/Antigravity                                    # Positional editor directory"
    echo -e "  $0 patch --port 8080                                         # Patch with custom port"
    echo -e "  $0 restore -e /opt/Antigravity                               # Restore editor original binary"
    echo -e "  $0 restart                                                   # Restart language_server process"
    echo ""
    exit 0
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        patch|restore|unpatch|status|restart|kill)
            COMMAND="$1"
            shift
            ;;
        -e|--editor)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                CUSTOM_TARGET="$2"
                shift 2
            else
                echo -e "${RED}Error: option $1 requires a path to editor directory${NC}"
                exit 1
            fi
            ;;
        -f|--file|--path)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                CUSTOM_TARGET="$2"
                shift 2
            else
                echo -e "${RED}Error: option $1 requires a path to file or directory${NC}"
                exit 1
            fi
            ;;
        --dir|--bin-dir)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                CUSTOM_TARGET="$2"
                shift 2
            else
                echo -e "${RED}Error: option --dir requires a directory path${NC}"
                exit 1
            fi
            ;;
        --port)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                PORT="$2"
                shift 2
            else
                echo -e "${RED}Error: option --port requires a port number${NC}"
                exit 1
            fi
            ;;
        --host)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                HOST="$2"
                shift 2
            else
                echo -e "${RED}Error: option --host requires a host address${NC}"
                exit 1
            fi
            ;;
        --url)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                CUSTOM_URL="$2"
                shift 2
            else
                echo -e "${RED}Error: option --url requires a valid URL${NC}"
                exit 1
            fi
            ;;
        --timeout)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                WAIT_TIMEOUT="$2"
                shift 2
            else
                echo -e "${RED}Error: option --timeout requires seconds${NC}"
                exit 1
            fi
            ;;
        --no-wait)
            WAIT_TIMEOUT=0
            shift
            ;;
        --no-watchdog)
            ENABLE_WATCHDOG=0
            shift
            ;;
        --watchdog)
            ENABLE_WATCHDOG=1
            shift
            ;;
        -y|--yes)
            AUTO_CONFIRM=true
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            # If argument looks like a path (contains / or exists on filesystem)
            if [[ "$1" == *"/"* || -e "$1" ]]; then
                CUSTOM_TARGET="$1"
                shift
            else
                echo -e "${RED}Unknown option: $1${NC}"
                echo -e "Use ${BOLD}$0 --help${NC} for usage information."
                exit 1
            fi
            ;;
    esac
done

# Resolve Target Proxy URL
if [[ -n "$CUSTOM_URL" ]]; then
    PROXY_URL="${CUSTOM_URL%/}"
else
    PROXY_URL="http://${HOST}:${PORT}"
fi

# Search for language_server within a directory (direct check, known subpaths, or recursive search)
find_ls_in_dir() {
    local dir="$1"
    [[ ! -d "$dir" ]] && return 1

    # 1. Check directly inside dir (e.g. if target is already the bin directory)
    for bname in "${KNOWN_BIN_NAMES[@]}"; do
        if [[ -f "${dir}/${bname}" || -f "${dir}/${bname}.real" ]]; then
            BIN_DIR="$(cd "$dir" && pwd)"
            LS_NAME="$bname"
            LS_FILE="${BIN_DIR}/${LS_NAME}"
            REAL_FILE="${BIN_DIR}/${LS_NAME}.real"
            return 0
        fi
    done

    # 2. Check known relative subpaths within editor installation directory
    for sub in "${KNOWN_SUBPATHS[@]}"; do
        if [[ -d "${dir}/${sub}" ]]; then
            for bname in "${KNOWN_BIN_NAMES[@]}"; do
                if [[ -f "${dir}/${sub}/${bname}" || -f "${dir}/${sub}/${bname}.real" ]]; then
                    BIN_DIR="$(cd "${dir}/${sub}" && pwd)"
                    LS_NAME="$bname"
                    LS_FILE="${BIN_DIR}/${LS_NAME}"
                    REAL_FILE="${BIN_DIR}/${LS_NAME}.real"
                    return 0
                fi
            done
        fi
    done

    # 3. Fallback recursive search inside directory tree (up to depth 8)
    local found=""
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        local fname
        fname="$(basename "$f")"
        fname="${fname%.real}"
        for bname in "${KNOWN_BIN_NAMES[@]}"; do
            if [[ "$fname" == "$bname" ]]; then
                BIN_DIR="$(cd "$(dirname "$f")" && pwd)"
                LS_NAME="$fname"
                LS_FILE="${BIN_DIR}/${LS_NAME}"
                REAL_FILE="${BIN_DIR}/${LS_NAME}.real"
                return 0
            fi
        done
        if [[ -z "$found" && "$fname" == language_server* ]]; then
            found="$f"
        fi
    done < <(find "$dir" -maxdepth 8 -type f \( -name "language_server*" \) ! -name "*.log" ! -name "*.txt" ! -name "*.md" ! -name "*.py" ! -name "*.sh" ! -name "*.json" 2>/dev/null)

    if [[ -n "$found" ]]; then
        local fname
        fname="$(basename "$found")"
        fname="${fname%.real}"
        BIN_DIR="$(cd "$(dirname "$found")" && pwd)"
        LS_NAME="$fname"
        LS_FILE="${BIN_DIR}/${LS_NAME}"
        REAL_FILE="${BIN_DIR}/${LS_NAME}.real"
        return 0
    fi

    return 1
}

# Locate Target Directory & Binary Name
resolve_target() {
    local target="$1"

    if [[ -n "$target" ]]; then
        # Expand leading tilde
        target="${target/#\~/$HOME}"

        # If target is an existing directory
        if [[ -d "$target" ]]; then
            if find_ls_in_dir "$target"; then
                return 0
            else
                echo -e "${RED}Error: Could not locate language_server binary in directory: ${target}${NC}" >&2
                return 1
            fi
        # If target is an existing file
        elif [[ -f "$target" || -e "$target" ]]; then
            local bname
            bname="$(basename "$target")"
            # If target itself is a language_server binary (or .real backup)
            if [[ "$bname" == language_server* ]]; then
                BIN_DIR="$(cd "$(dirname "$target")" && pwd)"
                LS_NAME="${bname%.real}"
                LS_FILE="${BIN_DIR}/${LS_NAME}"
                REAL_FILE="${BIN_DIR}/${LS_NAME}.real"
                return 0
            else
                # Target might be the main editor executable (e.g. /opt/Antigravity/antigravity or antigravity-ide)
                local parent_dir
                parent_dir="$(cd "$(dirname "$target")" && pwd)"
                if find_ls_in_dir "$parent_dir"; then
                    return 0
                else
                    echo -e "${RED}Error: Could not locate language_server binary in: ${parent_dir}${NC}" >&2
                    return 1
                fi
            fi
        # If target does not exist yet but parent directory exists
        elif [[ -d "$(dirname "$target")" ]]; then
            local bname
            bname="$(basename "$target")"
            if [[ "$bname" == language_server* ]]; then
                BIN_DIR="$(cd "$(dirname "$target")" && pwd)"
                LS_NAME="${bname%.real}"
                LS_FILE="${BIN_DIR}/${LS_NAME}"
                REAL_FILE="${BIN_DIR}/${LS_NAME}.real"
                return 0
            fi
            echo -e "${RED}Error: Path does not exist: ${target}${NC}" >&2
            return 1
        else
            echo -e "${RED}Error: Path does not exist: ${target}${NC}" >&2
            return 1
        fi
    fi

    # Try saved user configuration file (~/.config/agy-proxy/config.json)
    local config_file="${HOME}/.config/agy-proxy/config.json"
    if [[ -f "$config_file" ]]; then
        local cfg_ls cfg_ed
        cfg_ls=$(grep -o '"language_server_path"[[:space:]]*:[[:space:]]*"[^"]*"' "$config_file" 2>/dev/null | sed -E 's/.*"language_server_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/' || true)
        if [[ -n "$cfg_ls" && -f "$cfg_ls" ]]; then
            if resolve_target "$cfg_ls"; then
                return 0
            fi
        fi
        cfg_ed=$(grep -o '"editor_path"[[:space:]]*:[[:space:]]*"[^"]*"' "$config_file" 2>/dev/null | sed -E 's/.*"editor_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/' || true)
        if [[ -n "$cfg_ed" && -d "$cfg_ed" ]]; then
            if resolve_target "$cfg_ed"; then
                return 0
            fi
        fi
    fi

    # Try candidate directories
    for dir in "${CANDIDATE_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            if find_ls_in_dir "$dir"; then
                return 0
            fi
        fi
    done

    # If interactive and not found, ask user directly
    if [[ -t 0 ]]; then
        echo -e "${YELLOW}⚠️  Could not auto-detect Antigravity language_server path.${NC}"
        echo -e "Antigravity may be installed in a custom location."
        read -r -e -p "Enter path to editor directory or language_server file: " user_path
        if [[ -n "$user_path" ]]; then
            user_path="${user_path/#\~/$HOME}"
            user_path="${user_path%\"}"
            user_path="${user_path#\"}"
            user_path="${user_path%\'}"
            user_path="${user_path#\'}"
            if resolve_target "$user_path"; then
                mkdir -p "$(dirname "$config_file")"
                if command -v python3 >/dev/null 2>&1; then
                    python3 -c "import json, os; p='$config_file'; d=json.load(open(p)) if os.path.exists(p) else {}; d['language_server_path']='$LS_FILE'; json.dump(d, open(p,'w'), indent=2)" 2>/dev/null || true
                fi
                echo -e "${GREEN}✓ Saved language server binary to configuration:${NC} $LS_FILE"
                return 0
            fi
        fi
    fi

    echo -e "${RED}Error: Could not locate Antigravity language_server binary.${NC}" >&2
    echo -e "Please specify the editor or file manually using: ${BOLD}-e /opt/Antigravity${NC} or ${BOLD}-f /path/to/language_server${NC}" >&2
    echo -e "Or configure permanently with: ${BOLD}agy-proxy config set ls-path /path/to/language_server${NC}" >&2
    return 1
}

# Run command with sudo if target directory or file is not directly writable
run_privileged() {
    if [[ -w "$BIN_DIR" && (! -e "$LS_FILE" || -w "$LS_FILE") ]]; then
        "$@"
    else
        echo -e "${YELLOW}🔑 Elevated permissions required. Running: sudo $*${NC}"
        sudo "$@"
    fi
}

# Determine if a file is a shell wrapper script
is_wrapper_script() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        return 1
    fi
    if head -n 5 "$file" 2>/dev/null | grep -qE '^#!(/bin/sh|/bin/bash|/usr/bin/env)'; then
        return 0
    fi
    return 1
}

# Find running language_server PIDs (excluding this script)
get_running_pids() {
    local target_bin="$1"
    pgrep -f "language_server" 2>/dev/null | while read -r pid; do
        if [[ "$pid" == "$$" ]]; then
            continue
        fi
        local comm
        comm=$(ps -o comm= -p "$pid" 2>/dev/null || true)
        if [[ "$comm" == "bash" || "$comm" == "sh" ]]; then
            continue
        fi
        local cmd
        if [[ -f "/proc/$pid/cmdline" ]]; then
            cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
        else
            cmd=$(ps -o command= -p "$pid" 2>/dev/null || true)
        fi
        if [[ "$cmd" =~ patch_language_server ]] || [[ "$cmd" =~ agy_ls_watchdog ]]; then
            continue
        fi
        if [[ -n "$target_bin" ]]; then
            local exe=""
            if [[ -e "/proc/$pid/exe" ]]; then
                exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)
            fi
            if [[ -n "$exe" && "$exe" != "$target_bin" && ! "$cmd" =~ "$target_bin" ]]; then
                continue
            elif [[ -z "$exe" && ! "$cmd" =~ "$target_bin" ]]; then
                continue
            fi
        fi
        if [[ "$cmd" =~ language_server ]]; then
            echo "$pid"
        fi
    done
}

# Check if agy-proxy is responding
check_proxy_alive() {
    if curl -s -f -m 1 "${PROXY_URL}/health" > /dev/null 2>&1 || curl -s -f -m 1 "${PROXY_URL}/api/info" > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Generate the wrapper shell script
generate_wrapper() {
    local proxy_url="$1"
    local proxy_host="$2"
    local proxy_port="$3"
    local wait_timeout="$4"
    local real_bin_name="$5"
    local enable_watchdog="${6:-1}"

    cat << 'EOF'
#!/usr/bin/env bash
# ==============================================================================
# Antigravity Language Server Proxy Wrapper
# Intercepts IDE requests and routes them through agy-proxy
# Auto-Fallback (Direct Bypass): connects directly to Google if proxy is offline
# Live Auto-Switching: dynamic watchdog auto-detects proxy connect/disconnect
# Generated by agy-proxy patch_language_server.sh
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EOF
    cat << EOF
REAL_LS="\${SCRIPT_DIR}/${real_bin_name}"

# Default configuration (overrideable via environment variables)
PROXY_HOST="\${PROXY_HOST:-${proxy_host}}"
PROXY_PORT="\${PROXY_PORT:-${proxy_port}}"
PROXY_URL="\${AGY_PROXY_URL:-${proxy_url}}"
WAIT_TIMEOUT="\${AGY_PROXY_WAIT:-${wait_timeout}}"
ENABLE_WATCHDOG="\${AGY_PROXY_WATCHDOG:-${enable_watchdog}}"

# Default Google backend endpoints for Antigravity (native fallback)
DEFAULT_API_URL="https://generativelanguage.googleapis.com"
DEFAULT_CC_ENDPOINT="https://daily-cloudcode-pa.googleapis.com"

EOF
    cat << 'EOF'
if [ ! -f "$REAL_LS" ]; then
    echo "[wrapper] ❌ ERROR: Real binary not found at: $REAL_LS" >&2
    exit 1
fi

# Quick connectivity check for agy-proxy (/health or /api/info)
is_proxy_alive() {
    curl -sf --max-time 1 "${PROXY_URL}/health" > /dev/null 2>&1 || \
    curl -sf --max-time 1 "${PROXY_URL}/api/info" > /dev/null 2>&1
}

# Auto-Fallback Check: verify if agy-proxy is responding at startup
proxy_online=0
if is_proxy_alive; then
    proxy_online=1
elif [ "${WAIT_TIMEOUT}" -gt 0 ] 2>/dev/null; then
    elapsed=0
    while [ "$elapsed" -lt "$WAIT_TIMEOUT" ]; do
        sleep 1
        elapsed=$((elapsed + 1))
        if is_proxy_alive; then
            proxy_online=1
            break
        fi
    done
fi

TARGET_PID=$$
WATCHDOG_LOG="${TMPDIR:-/tmp}/agy_ls_watchdog.log"

if [ "$proxy_online" -eq 1 ]; then
    CURRENT_MODE="proxy"
    echo "[wrapper] ⚡ agy-proxy active at ${PROXY_URL} -> routing traffic through proxy" >&2
else
    CURRENT_MODE="direct"
    echo "[wrapper] ⚠️  agy-proxy offline / not responding at ${PROXY_URL} (timeout ${WAIT_TIMEOUT}s)" >&2
    echo "[wrapper] 🔄 Auto-Fallback: launching language_server in DIRECT mode (Google backend)" >&2
fi

# Reconstruct arguments:
# In PROXY mode: inject/point to PROXY_URL
# In DIRECT mode: ensure native Google backend endpoints are present (never default to 0.0.0.0:50001)
args=("$@")
FINAL_ARGS=()
has_api_url=0
has_cloud_endpoint=0

for ((i=0; i<${#args[@]}; i++)); do
    arg="${args[i]}"

    if [[ "$arg" == "--api_server_url" ]]; then
        next_val="${args[i+1]}"
        if [ "$CURRENT_MODE" = "proxy" ]; then
            FINAL_ARGS+=("$arg" "$PROXY_URL")
        else
            if [[ "$next_val" == *"127.0.0.1"* || "$next_val" == *"localhost"* || "$next_val" == "$PROXY_URL"* || -z "$next_val" ]]; then
                FINAL_ARGS+=("$arg" "$DEFAULT_API_URL")
            else
                FINAL_ARGS+=("$arg" "$next_val")
            fi
        fi
        has_api_url=1
        i=$((i+1))
    elif [[ "$arg" == --api_server_url=* ]]; then
        val="${arg#--api_server_url=}"
        if [ "$CURRENT_MODE" = "proxy" ]; then
            FINAL_ARGS+=("--api_server_url=$PROXY_URL")
        else
            if [[ "$val" == *"127.0.0.1"* || "$val" == *"localhost"* || "$val" == "$PROXY_URL"* || -z "$val" ]]; then
                FINAL_ARGS+=("--api_server_url=$DEFAULT_API_URL")
            else
                FINAL_ARGS+=("$arg")
            fi
        fi
        has_api_url=1
    elif [[ "$arg" == "--cloud_code_endpoint" ]]; then
        next_val="${args[i+1]}"
        if [ "$CURRENT_MODE" = "proxy" ]; then
            FINAL_ARGS+=("$arg" "$PROXY_URL")
        else
            if [[ "$next_val" == *"127.0.0.1"* || "$next_val" == *"localhost"* || "$next_val" == "$PROXY_URL"* || -z "$next_val" ]]; then
                FINAL_ARGS+=("$arg" "$DEFAULT_CC_ENDPOINT")
            else
                FINAL_ARGS+=("$arg" "$next_val")
            fi
        fi
        has_cloud_endpoint=1
        i=$((i+1))
    elif [[ "$arg" == --cloud_code_endpoint=* ]]; then
        val="${arg#--cloud_code_endpoint=}"
        if [ "$CURRENT_MODE" = "proxy" ]; then
            FINAL_ARGS+=("--cloud_code_endpoint=$PROXY_URL")
        else
            if [[ "$val" == *"127.0.0.1"* || "$val" == *"localhost"* || "$val" == "$PROXY_URL"* || -z "$val" ]]; then
                FINAL_ARGS+=("--cloud_code_endpoint=$DEFAULT_CC_ENDPOINT")
            else
                FINAL_ARGS+=("$arg")
            fi
        fi
        has_cloud_endpoint=1
    else
        FINAL_ARGS+=("$arg")
    fi
done

if [ "$has_api_url" -eq 0 ]; then
    if [ "$CURRENT_MODE" = "proxy" ]; then
        FINAL_ARGS+=("--api_server_url" "$PROXY_URL")
    else
        FINAL_ARGS+=("--api_server_url" "$DEFAULT_API_URL")
    fi
fi
if [ "$has_cloud_endpoint" -eq 0 ]; then
    if [ "$CURRENT_MODE" = "proxy" ]; then
        FINAL_ARGS+=("--cloud_code_endpoint" "$PROXY_URL")
    else
        FINAL_ARGS+=("--cloud_code_endpoint" "$DEFAULT_CC_ENDPOINT")
    fi
fi

# Live Auto-Switching: Watchdog monitors proxy connectivity and signals language_server when state changes
if [ "${ENABLE_WATCHDOG}" != "0" ]; then
    (
        exec </dev/null
        exec >> "$WATCHDOG_LOG" 2>&1

        WATCHDOG_PID_FILE="${TMPDIR:-/tmp}/agy_ls_watchdog_${TARGET_PID}.pid"
        echo "${BASHPID:-$$}" > "$WATCHDOG_PID_FILE"
        trap 'rm -f "$WATCHDOG_PID_FILE"' EXIT INT TERM

        # Prevent runaway log file growth
        if [ -f "$WATCHDOG_LOG" ] && [ "$(stat -c%s "$WATCHDOG_LOG" 2>/dev/null || stat -f%z "$WATCHDOG_LOG" 2>/dev/null || echo 0)" -gt 524288 ]; then
            tail -n 500 "$WATCHDOG_LOG" > "${WATCHDOG_LOG}.tmp" 2>/dev/null && mv "${WATCHDOG_LOG}.tmp" "$WATCHDOG_LOG" 2>/dev/null || true
        fi

        echo "$(date '+%Y-%m-%d %H:%M:%S') [watchdog] Started for PID ${TARGET_PID} in mode: ${CURRENT_MODE} (monitoring ${PROXY_URL})"

        # Initial grace period to allow newly spawned language_server to initialize and report port
        sleep 4

        consecutive_triggers=0
        TRIGGER_THRESHOLD=2

        while true; do
            # 1. Exit if the supervised language_server process has exited
            if ! kill -0 "$TARGET_PID" 2>/dev/null; then
                echo "$(date '+%Y-%m-%d %H:%M:%S') [watchdog] Supervised process ${TARGET_PID} exited. Terminating watchdog."
                exit 0
            fi

            # 2. Probe proxy health
            if curl -sf --max-time 1 "${PROXY_URL}/health" >/dev/null 2>&1 || \
               curl -sf --max-time 1 "${PROXY_URL}/api/info" >/dev/null 2>&1; then
                proxy_now=1
            else
                proxy_now=0
            fi

            # 3. Detect state changes
            if [ "$CURRENT_MODE" = "proxy" ]; then
                # In PROXY mode: detect if proxy went DOWN
                if [ "$proxy_now" -eq 0 ]; then
                    consecutive_triggers=$((consecutive_triggers + 1))
                    if [ "$consecutive_triggers" -ge "$TRIGGER_THRESHOLD" ]; then
                        echo "$(date '+%Y-%m-%d %H:%M:%S') [watchdog] ⚠️ agy-proxy disconnected! Signaling PID ${TARGET_PID} to switch to DIRECT mode..."
                        kill -TERM "$TARGET_PID" 2>/dev/null || true
                        exit 0
                    fi
                else
                    consecutive_triggers=0
                fi
            else
                # In DIRECT mode: detect if proxy came ONLINE
                if [ "$proxy_now" -eq 1 ]; then
                    consecutive_triggers=$((consecutive_triggers + 1))
                    if [ "$consecutive_triggers" -ge "$TRIGGER_THRESHOLD" ]; then
                        echo "$(date '+%Y-%m-%d %H:%M:%S') [watchdog] ⚡ agy-proxy detected online! Signaling PID ${TARGET_PID} to switch to PROXY mode..."
                        kill -TERM "$TARGET_PID" 2>/dev/null || true
                        exit 0
                    fi
                else
                    consecutive_triggers=0
                fi
            fi

            sleep 2
        done
    ) &
fi

exec "$REAL_LS" "${FINAL_ARGS[@]}"
EOF
}

# Kill running language_server instances
kill_running_instances() {
    local target_bin="${1:-}"
    local pids
    if [[ -n "$target_bin" ]]; then
        pids=$(get_running_pids "$target_bin")
    elif [[ -n "$REAL_FILE" ]]; then
        pids=$(get_running_pids "$REAL_FILE")
    else
        pids=$(get_running_pids)
    fi
    if [[ -z "$pids" ]]; then
        echo -e "${CYAN}ℹ️  No active language_server processes found for this target.${NC}"
        return 0
    fi

    echo -e "${YELLOW}Stopping active language_server processes (PIDs: ${pids//$'\n'/ })...${NC}"
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 1

    # Verify if any remained
    local remaining
    if [[ -n "$target_bin" ]]; then
        remaining=$(get_running_pids "$target_bin")
    elif [[ -n "$REAL_FILE" ]]; then
        remaining=$(get_running_pids "$REAL_FILE")
    else
        remaining=$(get_running_pids)
    fi
    if [[ -n "$remaining" ]]; then
        for pid in $remaining; do
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
    # Clean up watchdog daemon if running
    local watchdog_pid_file="${TMPDIR:-/tmp}/agy_ls_watchdog.pid"
    if [[ -f "$watchdog_pid_file" ]]; then
        local wpid
        wpid=$(cat "$watchdog_pid_file" 2>/dev/null || true)
        if [[ -n "$wpid" ]] && kill -0 "$wpid" 2>/dev/null; then
            kill "$wpid" 2>/dev/null || true
        fi
        rm -f "$watchdog_pid_file"
    fi

    echo -e "${GREEN}✅ Language server stopped. Antigravity IDE will respawn it automatically.${NC}"
}

# Status Command
do_status() {
    echo -e "\n${BOLD}${BLUE}======================================================${NC}"
    echo -e "${BOLD}${BLUE}⚡ Antigravity Language Server Status${NC}"
    echo -e "${BOLD}${BLUE}======================================================${NC}"
    echo -e "Target File:        ${CYAN}${LS_FILE}${NC}"
    echo -e "Directory:          ${CYAN}${BIN_DIR}${NC}"

    # Check Patch Status
    if is_wrapper_script "$LS_FILE"; then
        local configured_url
        configured_url=$(grep -E 'PROXY_URL="\$\{AGY_PROXY_URL:-' "$LS_FILE" 2>/dev/null | sed -E 's/.*:-([^}]+)\}.*/\1/' || echo "custom")
        local configured_timeout
        configured_timeout=$(grep -E 'WAIT_TIMEOUT="\$\{AGY_PROXY_WAIT:-' "$LS_FILE" 2>/dev/null | sed -E 's/.*:-([^}]+)\}.*/\1/' || echo "2")
        local configured_watchdog
        configured_watchdog=$(grep -E 'ENABLE_WATCHDOG="\$\{AGY_PROXY_WATCHDOG:-' "$LS_FILE" 2>/dev/null | sed -E 's/.*:-([^}]+)\}.*/\1/' || echo "1")
        echo -e "Patch Status:       ${GREEN}${BOLD}PATCHED (Wrapper Active)${NC}"
        echo -e "Configured Route:   ${CYAN}${configured_url}${NC}"
        echo -e "Wait Timeout:       ${YELLOW}${configured_timeout}s${NC}"
        if [[ "$configured_watchdog" == "1" ]]; then
            echo -e "Auto-Fallback:      ${GREEN}Active (Live auto-switching: Proxy ⇄ Direct Google)${NC}"
        else
            echo -e "Auto-Fallback:      ${YELLOW}Active (Startup-only fallback, Live watchdog disabled)${NC}"
        fi
    elif [[ -f "$LS_FILE" ]]; then
        echo -e "Patch Status:       ${YELLOW}NOT PATCHED (Original binary in place)${NC}"
    else
        echo -e "Patch Status:       ${RED}MISSING target binary (${LS_NAME})${NC}"
    fi

    # Check Backup Binary
    if [[ -f "$REAL_FILE" ]]; then
        local sz
        sz=$(du -h "$REAL_FILE" 2>/dev/null | cut -f1)
        echo -e "Backup Binary:      ${GREEN}Present${NC} (${sz}, $(basename "$REAL_FILE"))"
    else
        echo -e "Backup Binary:      ${YELLOW}None ($(basename "$REAL_FILE") not found)${NC}"
    fi

    # Check Proxy Connectivity
    echo -n "Proxy Connection:   "
    if check_proxy_alive; then
        echo -e "${GREEN}Active at ${PROXY_URL}${NC}"
    else
        echo -e "${YELLOW}Not responding at ${PROXY_URL}${NC}"
    fi

    # Check Running Process
    local pids
    pids=$(get_running_pids)
    echo -n "Active Processes:   "
    if [[ -n "$pids" ]]; then
        echo -e "${GREEN}Running (PID: ${pids//$'\n'/, })${NC}"
        for pid in $pids; do
            local cmd=""
            if [[ -f "/proc/$pid/cmdline" ]]; then
                cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
            else
                cmd=$(ps -o command= -p "$pid" 2>/dev/null || true)
            fi
            local mode_str="${YELLOW}UNKNOWN${NC}"
            if [[ "$cmd" =~ "googleapis.com" ]]; then
                mode_str="${CYAN}DIRECT (Google Backend: generativelanguage.googleapis.com)${NC}"
            elif [[ "$cmd" =~ ":8000" || "$cmd" =~ "127.0.0.1" ]]; then
                mode_str="${GREEN}PROXY (Traffic routed to agy-proxy)${NC}"
            fi
            echo -e "                    ${BOLD}↳ PID $pid Mode:${NC} $mode_str"
            echo -e "                      ${CYAN}${cmd:0:110}...${NC}"

            local wpid_file="${TMPDIR:-/tmp}/agy_ls_watchdog_${pid}.pid"
            local watchdog_info="${YELLOW}Inactive${NC}"
            if [[ -f "$wpid_file" ]]; then
                local wpid
                wpid=$(cat "$wpid_file" 2>/dev/null || true)
                if [[ -n "$wpid" ]] && kill -0 "$wpid" 2>/dev/null; then
                    watchdog_info="${GREEN}Active (PID: ${wpid})${NC}"
                fi
            else
                local child_wd
                child_wd=$(pgrep -P "$pid" 2>/dev/null | head -n 1 || true)
                if [[ -n "$child_wd" ]]; then
                    watchdog_info="${GREEN}Active (PID: ${child_wd})${NC}"
                fi
            fi
            echo -e "                      ${BOLD}Watchdog Daemon:${NC} ${watchdog_info}"
        done
    else
        echo -e "${YELLOW}Stopped${NC}"
    fi

    # Check Watchdog Activity Log
    local watchdog_log="${TMPDIR:-/tmp}/agy_ls_watchdog.log"
    if [[ -f "$watchdog_log" ]]; then
        echo -e "\n${BOLD}Recent Watchdog Events (last 5):${NC}"
        tail -n 5 "$watchdog_log" 2>/dev/null | while read -r logline; do
            echo -e "  ${CYAN}•${NC} $logline"
        done
    fi

    echo -e "${BOLD}${BLUE}======================================================${NC}\n"
}

# Patch Command
do_patch() {
    echo -e "\n${BOLD}${CYAN}🔧 Patching Antigravity Language Server${NC}"
    echo -e "Target File:        ${BLUE}${LS_FILE}${NC}"
    echo -e "Directory:          ${BLUE}${BIN_DIR}${NC}"
    echo -e "Route Requests To:  ${GREEN}${PROXY_URL}${NC}"
    echo -e "Proxy Wait Timeout: ${YELLOW}${WAIT_TIMEOUT}s${NC}"
    if [[ "$ENABLE_WATCHDOG" == "1" ]]; then
        echo -e "Auto-Fallback:      ${GREEN}Active (Live auto-switching: Proxy ⇄ Direct Google)${NC}\n"
    else
        echo -e "Auto-Fallback:      ${YELLOW}Active (Startup-only fallback, Live watchdog disabled)${NC}\n"
    fi

    # Step 1: Ensure real binary exists
    if [[ -f "$REAL_FILE" ]]; then
        if ! is_wrapper_script "$REAL_FILE"; then
            echo -e "${GREEN}✓ Found existing backup binary:${NC} $(basename "$REAL_FILE")"
        else
            echo -e "${RED}❌ Error: $(basename "$REAL_FILE") appears to be a shell script, not the original binary!${NC}"
            echo -e "Please verify your files in ${BIN_DIR} before proceeding."
            exit 1
        fi
    elif [[ -f "$LS_FILE" ]]; then
        if is_wrapper_script "$LS_FILE"; then
            echo -e "${RED}❌ Error: $(basename "$LS_FILE") is already a wrapper script, but $(basename "$REAL_FILE") was not found!${NC}"
            echo -e "Original binary backup is missing. Refusing to overwrite."
            exit 1
        fi
        echo -e "${CYAN}📦 Backing up original binary:${NC} $(basename "$LS_FILE") -> $(basename "$REAL_FILE")"
        run_privileged mv "$LS_FILE" "$REAL_FILE"
        run_privileged chmod +x "$REAL_FILE"
    else
        echo -e "${RED}❌ Error: Neither $(basename "$LS_FILE") nor $(basename "$REAL_FILE") found in ${BIN_DIR}${NC}"
        exit 1
    fi

    # Step 2: Write temporary wrapper and atomically place it
    local tmp_wrapper
    tmp_wrapper=$(mktemp)
    generate_wrapper "$PROXY_URL" "$HOST" "$PORT" "$WAIT_TIMEOUT" "$(basename "$REAL_FILE")" "$ENABLE_WATCHDOG" > "$tmp_wrapper"
    chmod +x "$tmp_wrapper"

    echo -e "${CYAN}⚡ Installing new $(basename "$LS_FILE") wrapper script...${NC}"
    run_privileged cp "$tmp_wrapper" "$LS_FILE"
    run_privileged chmod 755 "$LS_FILE"
    rm -f "$tmp_wrapper"

    echo -e "${GREEN}✅ Successfully patched $(basename "$LS_FILE")!${NC}"

    # Step 3: Prompt to restart running instances
    local pids
    pids=$(get_running_pids "$REAL_FILE")
    if [[ -z "$pids" ]]; then
        pids=$(get_running_pids "$LS_FILE")
    fi
    if [[ -n "$pids" ]]; then
        echo ""
        if [[ "$AUTO_CONFIRM" == "true" ]]; then
            kill_running_instances "$REAL_FILE"
        elif [[ -t 0 ]]; then
            read -r -p "Restart running language_server now to apply changes? [Y/n]: " choice
            choice="${choice:-Y}"
            if [[ "$choice" =~ ^[Yy]$ ]]; then
                kill_running_instances "$REAL_FILE"
            fi
        fi
    fi
}

# Restore / Unpatch Command
do_restore() {
    echo -e "\n${BOLD}${YELLOW}⏪ Restoring Original Antigravity Language Server${NC}"
    echo -e "Target File:      ${BLUE}${LS_FILE}${NC}"
    echo -e "Backup File:      ${BLUE}${REAL_FILE}${NC}\n"

    if [[ ! -f "$REAL_FILE" ]]; then
        echo -e "${RED}❌ Error: Backup binary $(basename "$REAL_FILE") does not exist!${NC}"
        echo -e "Cannot restore original binary."
        exit 1
    fi

    if is_wrapper_script "$REAL_FILE"; then
        echo -e "${RED}❌ Error: $(basename "$REAL_FILE") is a script, not the original executable binary!${NC}"
        exit 1
    fi

    if [[ "$AUTO_CONFIRM" != "true" && -t 0 ]]; then
        read -r -p "Are you sure you want to restore the original unpatched binary? [y/N]: " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            echo -e "Restoration cancelled."
            exit 0
        fi
    fi

    echo -e "${CYAN}Restoring:${NC} $(basename "$REAL_FILE") -> $(basename "$LS_FILE")"
    run_privileged rm -f "$LS_FILE"
    run_privileged mv "$REAL_FILE" "$LS_FILE"
    run_privileged chmod 755 "$LS_FILE"

    echo -e "${GREEN}✅ Original $(basename "$LS_FILE") successfully restored!${NC}"

    local pids
    pids=$(get_running_pids "$LS_FILE")
    if [[ -n "$pids" ]]; then
        echo ""
        if [[ "$AUTO_CONFIRM" == "true" ]]; then
            kill_running_instances "$LS_FILE"
        elif [[ -t 0 ]]; then
            read -r -p "Restart running language_server now? [Y/n]: " choice
            choice="${choice:-Y}"
            if [[ "$choice" =~ ^[Yy]$ ]]; then
                kill_running_instances "$LS_FILE"
            fi
        fi
    fi
}

# Change Target File Path Interactively
change_path_interactive() {
    echo ""
    read -r -e -p "Enter new path to editor directory or language_server file: " new_path
    if [[ -n "$new_path" ]]; then
        if resolve_target "$new_path"; then
            echo -e "${GREEN}✓ Target updated:${NC} ${LS_FILE}"
        fi
    fi
}

# Main Execution Flow
resolve_target "$CUSTOM_TARGET" || exit 1

case "$COMMAND" in
    patch)
        do_patch
        ;;
    restore|unpatch)
        do_restore
        ;;
    status)
        do_status
        ;;
    restart|kill)
        kill_running_instances
        ;;
    "")
        # Interactive Mode if running in terminal with no arguments
        if [[ -t 0 ]]; then
            while true; do
                do_status
                echo -e "${BOLD}Select an action:${NC}"
                echo -e "  ${CYAN}1)${NC} Patch / Update wrapper (route to ${PROXY_URL})"
                echo -e "  ${CYAN}2)${NC} Restore original binary (unpatch)"
                echo -e "  ${CYAN}3)${NC} Restart running language_server"
                echo -e "  ${CYAN}4)${NC} Refresh status"
                echo -e "  ${CYAN}5)${NC} Change target file path"
                echo -e "  ${CYAN}6)${NC} Exit"
                echo ""
                read -r -p "Enter choice [1-6]: " menu_choice
                case "$menu_choice" in
                    1) do_patch; break ;;
                    2) do_restore; break ;;
                    3) kill_running_instances; break ;;
                    4) continue ;;
                    5) change_path_interactive; continue ;;
                    6) exit 0 ;;
                    *) echo -e "${RED}Invalid choice${NC}" ;;
                esac
            done
        else
            do_status
        fi
        ;;
esac
