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
CUSTOM_TARGET="${ANTIGRAVITY_LS_PATH:-${ANTIGRAVITY_FILE:-${ANTIGRAVITY_BIN_DIR:-${ANTIGRAVITY_EDITOR_PATH:-${ANTIGRAVITY_EDITOR_DIR:-}}}}}"
AUTO_CONFIRM=false
COMMAND=""

# Known candidate directories for Antigravity 2.0 and Antigravity IDE (Standalone)
CANDIDATE_DIRS=(
    # Google Antigravity 2.0 (Hub / Desktop App)
    "/opt/Antigravity/resources/bin"
    "/opt/Antigravity"
    "/opt/antigravity/resources/bin"
    "/opt/antigravity"
    "${HOME}/.local/share/Antigravity/resources/bin"
    "${HOME}/.local/share/Antigravity"
    "/usr/lib/antigravity/resources/bin"
    "/usr/lib/antigravity"
    "/Applications/Antigravity.app/Contents/Resources/app/resources/bin"
    "/Applications/Antigravity.app/Contents/Resources/bin"
    "/Applications/Antigravity.app"

    # Google Antigravity IDE (Standalone Dedicated Editor)
    "/opt/Antigravity IDE/resources/app/extensions/antigravity/bin"
    "/opt/Antigravity IDE"
    "/opt/antigravity-ide/resources/app/extensions/antigravity/bin"
    "/opt/antigravity-ide"
    "${HOME}/.local/share/Antigravity IDE/resources/app/extensions/antigravity/bin"
    "${HOME}/.local/share/Antigravity IDE"
    "${HOME}/Downloads/Antigravity IDE/Antigravity IDE/resources/app/extensions/antigravity/bin"
    "${HOME}/Downloads/Antigravity IDE/Antigravity IDE"
    "${HOME}/Downloads/Antigravity IDE"
    "/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin"
    "/Applications/Antigravity IDE.app"
)

KNOWN_BIN_NAMES=(
    "language_server"
    "language_server_linux_x64"
    "language_server_linux_arm64"
    "language_server_darwin_arm64"
    "language_server_darwin_x64"
    "language_server_windows_x64.exe"
)

# Known relative subpaths within editor installation root
KNOWN_SUBPATHS=(
    "resources/bin"
    "resources/app/extensions/antigravity/bin"
    "resources/app/resources/bin"
    "Contents/Resources/bin"
    "Contents/Resources/app/resources/bin"
    "Contents/Resources/app/extensions/antigravity/bin"
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
        read -r -e -p "Enter path to editor directory or language_server file: " user_path
        if [[ -n "$user_path" ]]; then
            resolve_target "$user_path"
            return $?
        fi
    fi

    echo -e "${RED}Error: Could not locate Antigravity language_server binary.${NC}" >&2
    echo -e "Please specify the editor or file manually using: ${BOLD}-e /opt/Antigravity${NC} or ${BOLD}-f /path/to/language_server${NC}" >&2
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
    pgrep -f "language_server" 2>/dev/null | while read -r pid; do
        if [[ "$pid" == "$$" ]]; then
            continue
        fi
        local cmd
        if [[ -f "/proc/$pid/cmdline" ]]; then
            cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
        else
            cmd=$(ps -o command= -p "$pid" 2>/dev/null || true)
        fi
        if [[ "$cmd" =~ patch_language_server ]]; then
            continue
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

    cat << 'EOF'
#!/usr/bin/env bash
# ==============================================================================
# Antigravity Language Server Proxy Wrapper
# Intercepts IDE requests and routes them through agy-proxy
# Auto-Fallback (Direct Bypass): connects directly to Google if proxy is offline
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

# Auto-Fallback Check: verify if agy-proxy is responding
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

if [ "$proxy_online" -eq 1 ]; then
    echo "[wrapper] ⚡ agy-proxy active at ${PROXY_URL} -> routing traffic through proxy" >&2

    # Rewrite/inject proxy parameters
    NEW_ARGS=()
    skip_next=0
    has_api_url=0
    has_cloud_endpoint=0

    for arg in "$@"; do
        if [ "$skip_next" -eq 1 ]; then
            skip_next=0
            continue
        fi

        if [[ "$arg" == "--api_server_url" ]]; then
            NEW_ARGS+=("$arg" "$PROXY_URL")
            has_api_url=1
            skip_next=1
        elif [[ "$arg" == "--cloud_code_endpoint" ]]; then
            NEW_ARGS+=("$arg" "$PROXY_URL")
            has_cloud_endpoint=1
            skip_next=1
        elif [[ "$arg" == --api_server_url=* ]]; then
            NEW_ARGS+=("--api_server_url=$PROXY_URL")
            has_api_url=1
        elif [[ "$arg" == --cloud_code_endpoint=* ]]; then
            NEW_ARGS+=("--cloud_code_endpoint=$PROXY_URL")
            has_cloud_endpoint=1
        else
            NEW_ARGS+=("$arg")
        fi
    done

    if [ "$has_api_url" -eq 0 ]; then
        NEW_ARGS+=("--api_server_url" "$PROXY_URL")
    fi
    if [ "$has_cloud_endpoint" -eq 0 ]; then
        NEW_ARGS+=("--cloud_code_endpoint" "$PROXY_URL")
    fi

    exec "$REAL_LS" "${NEW_ARGS[@]}"
else
    echo "[wrapper] ⚠️  agy-proxy offline / not responding at ${PROXY_URL} (timeout ${WAIT_TIMEOUT}s)" >&2
    echo "[wrapper] 🔄 Auto-Fallback: launching language_server in DIRECT mode (Google backend)" >&2

    # Filter out any lingering proxy parameters if present in "$@"
    CLEAN_ARGS=()
    skip_next=0
    has_proxy_arg=0
    for arg in "$@"; do
        if [ "$skip_next" -eq 1 ]; then
            skip_next=0
            continue
        fi
        if [ "$arg" = "--api_server_url" ] || [ "$arg" = "--cloud_code_endpoint" ]; then
            has_proxy_arg=1
            skip_next=1
            continue
        elif [[ "$arg" == --api_server_url=* ]] || [[ "$arg" == --cloud_code_endpoint=* ]]; then
            has_proxy_arg=1
            continue
        fi
        CLEAN_ARGS+=("$arg")
    done

    if [ "$has_proxy_arg" -eq 1 ]; then
        exec "$REAL_LS" "${CLEAN_ARGS[@]}"
    else
        exec "$REAL_LS" "$@"
    fi
fi
EOF
}

# Kill running language_server instances
kill_running_instances() {
    local pids
    pids=$(get_running_pids)
    if [[ -z "$pids" ]]; then
        echo -e "${CYAN}ℹ️  No active language_server processes found.${NC}"
        return 0
    fi

    echo -e "${YELLOW}Stopping active language_server processes (PIDs: ${pids//$'\n'/ })...${NC}"
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 1

    # Verify if any remained
    local remaining
    remaining=$(get_running_pids)
    if [[ -n "$remaining" ]]; then
        for pid in $remaining; do
            kill -9 "$pid" 2>/dev/null || true
        done
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
        echo -e "Patch Status:       ${GREEN}${BOLD}PATCHED (Wrapper Active)${NC}"
        echo -e "Configured Route:   ${CYAN}${configured_url}${NC}"
        echo -e "Wait Timeout:       ${YELLOW}${configured_timeout}s${NC}"
        echo -e "Auto-Fallback:      ${GREEN}Active (Direct Bypass if proxy offline)${NC}"
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
        ps -o pid,command -p "${pids//$'\n'/,}" 2>/dev/null | tail -n +2 | while read -r line; do
            echo -e "                    ${CYAN}↳ ${line:0:110}...${NC}"
        done
    else
        echo -e "${YELLOW}Stopped${NC}"
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
    echo -e "Auto-Fallback:      ${GREEN}Active (Direct bypass if proxy offline)${NC}\n"

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
    generate_wrapper "$PROXY_URL" "$HOST" "$PORT" "$WAIT_TIMEOUT" "$(basename "$REAL_FILE")" > "$tmp_wrapper"
    chmod +x "$tmp_wrapper"

    echo -e "${CYAN}⚡ Installing new $(basename "$LS_FILE") wrapper script...${NC}"
    run_privileged cp "$tmp_wrapper" "$LS_FILE"
    run_privileged chmod 755 "$LS_FILE"
    rm -f "$tmp_wrapper"

    echo -e "${GREEN}✅ Successfully patched $(basename "$LS_FILE")!${NC}"

    # Step 3: Prompt to restart running instances
    local pids
    pids=$(get_running_pids)
    if [[ -n "$pids" ]]; then
        echo ""
        if [[ "$AUTO_CONFIRM" == "true" ]]; then
            kill_running_instances
        elif [[ -t 0 ]]; then
            read -r -p "Restart running language_server now to apply changes? [Y/n]: " choice
            choice="${choice:-Y}"
            if [[ "$choice" =~ ^[Yy]$ ]]; then
                kill_running_instances
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
    pids=$(get_running_pids)
    if [[ -n "$pids" ]]; then
        echo ""
        if [[ "$AUTO_CONFIRM" == "true" ]]; then
            kill_running_instances
        elif [[ -t 0 ]]; then
            read -r -p "Restart running language_server now? [Y/n]: " choice
            choice="${choice:-Y}"
            if [[ "$choice" =~ ^[Yy]$ ]]; then
                kill_running_instances
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
