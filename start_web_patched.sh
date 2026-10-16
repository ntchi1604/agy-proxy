#!/usr/bin/env bash
# ==============================================================================
# Antigravity Patched Web Hub (Experimental Auto-Extractor & Runner)
#
# Part of agy-proxy (https://github.com/qumhab/agy-proxy)
#
# This experimental script automatically:
# 1. Locates the language_server binary (auto-detected or manually specified)
# 2. Scans and extracts the embedded Web UI zip archive (304 web assets)
# 3. Applies non-destructive patches to the extracted assets:
#    - Unlocks Web Terminal on local/custom domains (bypasses non-corp lock)
#    - Enables File Explorer tab, Battle Mode, Autonomous Mode switch,
#      Inline Action cards, Thought Steering & Editing, Split View
#    - Disables broken Google3 Piper/blaze dependencies (Regroup Google3 Chats,
#      Agent Team blaze script, Concierge/Chief of Staff par archive)
# 4. Launches language_server with --web_bundle_path pointing to patched assets
# ==============================================================================

set -e

# Default paths
DEFAULT_LS_BIN="/opt/Antigravity/resources/bin/language_server"
DEFAULT_BUNDLE_DIR="${HOME}/.config/agy-proxy/web_ui"

LS_BIN="${LS_PATH:-$DEFAULT_LS_BIN}"
BUNDLE_DIR="${BUNDLE_PATH:-$DEFAULT_BUNDLE_DIR}"
PORT=""
FORCE_EXTRACT=0
VERBOSE=0
KILL_ELECTRON=0
RESTART=0
AUTO_OPEN=0
BROWSER_CMD=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -b|--bin|--ls-path)
            LS_BIN="$2"
            shift 2
            ;;
        --bin=*|--ls-path=*)
            LS_BIN="${1#*=}"
            shift
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        --port=*)
            PORT="${1#*=}"
            shift
            ;;
        -d|--bundle-dir|--dir)
            BUNDLE_DIR="$2"
            shift 2
            ;;
        --bundle-dir=*|--dir=*)
            BUNDLE_DIR="${1#*=}"
            shift
            ;;
        -f|--force|--extract|--repatch)
            FORCE_EXTRACT=1
            shift
            ;;
        -k|--kill-electron)
            KILL_ELECTRON=1
            shift
            ;;
        -r|--restart)
            RESTART=1
            shift
            ;;
        -o|--open)
            AUTO_OPEN=1
            shift
            ;;
        --no-open)
            AUTO_OPEN=0
            shift
            ;;
        --browser)
            BROWSER_CMD="$2"
            shift 2
            ;;
        --browser=*)
            BROWSER_CMD="${1#*=}"
            shift
            ;;
        -v|--verbose|--debug)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options] [ls_path] [port]"
            echo ""
            echo "Options:"
            echo "  -b, --bin <path>         Path to language_server (or language_server.real)"
            echo "  -p, --port <port>        Port for HTTPS web server (default: 44741 or 44742)"
            echo "  -d, --bundle-dir <path>  Target directory for extracted & patched bundle"
            echo "                           (default: ~/.config/agy-proxy/web_ui)"
            echo "  -f, --force              Force re-extracting and re-patching bundle"
            echo "  -k, --kill-electron      Automatically terminate running Electron instances"
            echo "  -r, --restart            Restart web server (terminate any instance on port)"
            echo "  -o, --open               Automatically open web browser on startup"
            echo "      --browser <cmd>      Specify custom browser executable (e.g. helium, google-chrome)"
            echo "  -v, --verbose, --debug   Show raw language_server console output (default: logged to file)"
            echo "  -h, --help               Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0"
            echo "  $0 -k"
            echo "  $0 -r"
            echo "  $0 -p 44742"
            echo "  $0 /opt/Antigravity/resources/bin/language_server"
            echo "  $0 -b /opt/Antigravity/resources/bin/language_server.real -p 44742 -f"
            exit 0
            ;;
        *)
            if [[ "$1" =~ ^[0-9]+$ ]] && [ -z "$PORT" ]; then
                PORT="$1"
            elif [ -f "$1" ]; then
                LS_BIN="$1"
            fi
            shift
            ;;
    esac
done

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}================================================================${NC}"
echo -e "${BOLD}🧪 Antigravity Patched Web Hub (Experimental Runner)${NC}"
echo -e "${CYAN}================================================================${NC}"

# Locate language_server
if [ ! -f "$LS_BIN" ]; then
    if [ -f "${LS_BIN}.real" ]; then
        LS_BIN="${LS_BIN}.real"
    else
        echo -e "${RED}❌ Error: language_server not found at: ${LS_BIN}${NC}" >&2
        echo "Specify path manually: $0 -b /path/to/language_server" >&2
        exit 1
    fi
fi

# Resolve to real ELF binary for zip extraction
REAL_LS="$LS_BIN"
if [ -f "$LS_BIN" ]; then
    if ! head -c 4 "$LS_BIN" | grep -q "ELF"; then
        DIR_NAME="$(dirname "$LS_BIN")"
        if [ -f "${DIR_NAME}/language_server.real" ]; then
            REAL_LS="${DIR_NAME}/language_server.real"
        fi
    fi
fi

echo -e "🔍 Language Server binary: ${BOLD}${REAL_LS}${NC}"
echo -e "📦 Web bundle directory:   ${BOLD}${BUNDLE_DIR}${NC}"

# Check if extraction / patching is required (auto-repatch if fix is missing)
NEEDS_EXTRACT=0
if [ "$FORCE_EXTRACT" -eq 1 ] || [ ! -d "$BUNDLE_DIR" ] || [ ! -f "$BUNDLE_DIR/main.js" ] || [ ! -f "$BUNDLE_DIR/index.html" ] || ! grep -q 'typeof a.getState==="function"' "$BUNDLE_DIR/main.js" 2>/dev/null; then
    NEEDS_EXTRACT=1
fi

if [ "$NEEDS_EXTRACT" -eq 1 ]; then
    echo -e "\n${YELLOW}⚙️  Extracting embedded Web UI zip and applying feature patches...${NC}"
    
    python3 - << EOF
import sys, os, zipfile, io, struct

binary_path = "$REAL_LS"
out_dir = "$BUNDLE_DIR"
os.makedirs(out_dir, exist_ok=True)

# 1. Scan binary for embedded zip using EOCD signatures
print(f"[*] Scanning binary: {binary_path}")
with open(binary_path, 'rb') as f:
    data = f.read()

eocd_sig = b'PK\x05\x06'
pos = 0
web_zip_data = None

while True:
    idx = data.find(eocd_sig, pos)
    if idx == -1: break
    eocd_data = data[idx:idx+22]
    if len(eocd_data) == 22:
        sig, disk1, disk2, count1, count2, cd_size, cd_offset = struct.unpack('<IHHHHII', eocd_data[:20])
        calc_start = idx - cd_size - cd_offset
        if 0 <= calc_start < idx:
            try:
                candidate = data[calc_start:idx+22]
                z = zipfile.ZipFile(io.BytesIO(candidate))
                names = z.namelist()
                if 'main.js' in names and 'index.html' in names:
                    web_zip_data = candidate
                    print(f"[*] Found embedded Web UI zip ({len(names)} files)")
                    break
            except Exception:
                pass
    pos = idx + 4

if not web_zip_data:
    sys.exit(f"❌ Error: Failed to locate Web UI zip archive inside {binary_path}")

# 2. Extract files
print(f"[*] Extracting files to: {out_dir}")
with zipfile.ZipFile(io.BytesIO(web_zip_data)) as z:
    z.extractall(out_dir)

# 3. Patch main.js
main_js_path = os.path.join(out_dir, 'main.js')
if not os.path.isfile(main_js_path):
    sys.exit("❌ Error: main.js not found after extraction")

with open(main_js_path, 'r', encoding='utf-8') as f:
    js = f.read()

print("[*] Applying patches to main.js...")

# Unlock Terminal domain restriction
t1 = '{runtimeGating:{host:[Qi.Web],userCohort:["google"],customFlag:"enable-jetbox-terminal-v2",isInIframe:!1,isDevMode:!1},feature:{terminalCapabilities:cV,showCorpPasswordWarning:!0,restrictToCorpDomain:!0}}'
r1 = '{runtimeGating:{host:[Qi.Web],userCohort:["google"],customFlag:"enable-jetbox-terminal-v2",isInIframe:!1,isDevMode:!1},feature:{terminalCapabilities:cV,showCorpPasswordWarning:!1,restrictToCorpDomain:!1}}'
js = js.replace(t1, r1)

t2 = 'n=!!a?.restrictToCorpDomain&&\ntypeof window!=="undefined"&&window.location.hostname!=="jetski.corp.google.com"'
r2 = 'n=!1'
js = js.replace(t2, r2)

t3 = 'return c?.restrictToCorpDomain&&typeof window!=="undefined"&&window.location.hostname!=="jetski.corp.google.com"?A.createElement(B5b,null):A.createElement("div",{"data-testid":"terminal-tab-surface"'
r3 = 'return A.createElement("div",{"data-testid":"terminal-tab-surface"'
js = js.replace(t3, r3)

# Disable Google3 Chat Migration warning card
t4 = 'projectV5Migration:{feature:{enabled:!1,regroupCard:null},applyFirst:[{runtimeGating:{userCohort:["google"]},feature:Lcc}]}'
r4 = 'projectV5Migration:{feature:{enabled:!1,regroupCard:null}}'
js = js.replace(t4, r4)

t5 = 'zeb=["App","Jetski Chat","Regroup Google3 Chats"]'
r5 = 'zeb=["App","Jetski Chat"]'
js = js.replace(t5, r5)

# Disable broken Agent Team blaze run script (use void 0 so Pj safely falls back to Ai dummy store)
js = js.replace('enabled:nk(L,"enable-agent-team")', 'enabled:void 0')

# Robustness: Guard Mj and Pj hooks against non-store arguments (e.g. boolean flags, null, undefined)
t_mj = 'var Mj=(a,b,...c)=>{var e=b.selector,f=b.equalityFn'
r_mj = 'var Mj=(a,b,...c)=>{a=a&&typeof a.getState==="function"?a:Ai;var e=b.selector,f=b.equalityFn'
js = js.replace(t_mj, r_mj)

t_pj = 'Pj=a=>Mj(a??Ai,{selector:Gi});'
r_pj = 'Pj=a=>Mj(a&&typeof a.getState==="function"?a:Ai,{selector:Gi});'
js = js.replace(t_pj, r_pj)

# Remove broken Concierge / Chief of Staff archive
t6 = 'conciergeAgent:{label:"Chief of Staff",description:"A permanent Chief of Staff conversation in the sidebar that manages your other conversations: delegate tasks, check status, and read results from one place.",\nsettingKey:Ui.CONCIERGE_AGENT_ENABLED,customFlag:"labs-concierge-agent",visibilityCustomFlag:"enable-concierge-agent"},'
js = js.replace(t6, '')

t7 = 'conciergeAgent:{feature:{enabled:!1},applyAll:[{runtimeGating:{customFlag:Zz.conciergeAgent.customFlag},feature:{enabled:!0}}]}'
r7 = 'conciergeAgent:{feature:{enabled:!1}}'
js = js.replace(t7, r7)

with open(main_js_path, 'w', encoding='utf-8') as f:
    f.write(js)

# 4. Patch index.html
index_html_path = os.path.join(out_dir, 'index.html')
with open(index_html_path, 'r', encoding='utf-8') as f:
    html = f.read()

print("[*] Applying auto-provisioning script to index.html...")
init_script = '''    <script>
      // Antigravity Web Hub: Auto-unlock Developer & Google-internal capabilities
      try {
        if (window.__APP_CONFIG__) {
          window.__APP_CONFIG__.devMode = true;
        }
        var curEnv = JSON.parse(localStorage.getItem("jetski.developer.featureEnvironmentOverride") || "{}");
        if (!curEnv.enabled || curEnv.userCohort !== "google") {
          localStorage.setItem("jetski.developer.featureEnvironmentOverride", JSON.stringify({
            enabled: true,
            userCohort: "google"
          }));
        }
        var curFlags = JSON.parse(localStorage.getItem("jetski.developer.customFlagOverrides") || "{}");
        var flagsToSet = {
          "enable-jetbox-terminal-v2": true,
          "enable-hub-builtin-browser": true,
          "enable-file-explorer-tab": true,
          "enable-battle-mode": true,
          "enable-thought-editing": true,
          "enable-thought-steering-from-selection": true,
          "enable-conversation-forking": true,
          "labs-autonomous-mode": true,
          "jetski-autonomous-mode": true,
          "labs-inline-actions": true,
          "enable-developer-mode": true,
          "enable-split-view": true,
          "enable-conversation-search-v2": true,
          "enable-pdf-viewer": true,
          "enable-plugins": true,
          "enable-trajectory-debug-tools": true
        };
        delete curFlags["enable-agent-team"];
        delete curFlags["enable-concierge-agent"];
        delete curFlags["labs-concierge-agent"];
        localStorage.removeItem("jetski.settings.conciergeAgentEnabled");
        localStorage.removeItem("jetski.settings.conciergeAgent");
        var changed = false;
        for (var k in flagsToSet) {
          if (curFlags[k] !== flagsToSet[k]) {
            curFlags[k] = flagsToSet[k];
            changed = true;
          }
        }
        if (changed) {
          localStorage.setItem("jetski.developer.customFlagOverrides", JSON.stringify(curFlags));
        }
      } catch (e) {
        console.warn("Auto-provision flags failed:", e);
      }
    </script>
  </head>'''

if 'Auto-unlock Developer' not in html:
    html = html.replace('  </head>', init_script)
    with open(index_html_path, 'w', encoding='utf-8') as f:
        f.write(html)

print("[+] Bundle successfully extracted and patched!")
EOF

    echo -e "${GREEN}✅ Web bundle ready at: ${BUNDLE_DIR}${NC}\n"
else
    echo -e "⚡ Using existing patched bundle (use ${BOLD}-f${NC} to force re-extraction)"
fi

# Restart handling
if [ "$RESTART" -eq 1 ]; then
    echo -e "${YELLOW}🔄 Restart requested: terminating existing language_server instances...${NC}"
    if [ -n "$PORT" ]; then
        pkill -f "language_server.*--https_server_port.*$PORT" 2>/dev/null || true
    else
        pkill -f "language_server.*--https_server_port.*44741" 2>/dev/null || true
        pkill -f "language_server.*--https_server_port.*44742" 2>/dev/null || true
    fi
    pkill -f "language_server.*--standalone" 2>/dev/null || true
    sleep 1
fi

# Electron instance handling
if pgrep -f "/opt/Antigravity/antigravity" >/dev/null 2>&1 || pgrep -f "antigravity-ide" >/dev/null 2>&1; then
    if [ "$KILL_ELECTRON" -eq 1 ]; then
        echo -e "${YELLOW}🧹 Stopping running Electron processes to free ~1.6 GB RAM...${NC}"
        pkill -f "/opt/Antigravity/antigravity" 2>/dev/null || true
        pkill -f "antigravity-ide" 2>/dev/null || true
        sleep 1
    else
        echo -e "${YELLOW}⚠️  Notice: Electron Antigravity window detected.${NC}"
        echo "   Tip: Close Electron or run '$0 -k' to free 1.6+ GB of RAM."
    fi
fi

# Port selection
if [ -z "$PORT" ]; then
    if ss -tulpn 2>/dev/null | grep -q ":44741\b" || netstat -tulpn 2>/dev/null | grep -q ":44741\b"; then
        PORT="44742"
    else
        PORT="44741"
    fi
fi

# Proxy health check
PROXY_PORT="${AGY_PROXY_PORT:-8000}"
PROXY_URL="${AGY_PROXY_URL:-http://127.0.0.1:${PROXY_PORT}}"
PROXY_ONLINE=0

if curl -sf --max-time 1 "${PROXY_URL}/health" >/dev/null 2>&1 || curl -sf --max-time 1 "${PROXY_URL}/api/info" >/dev/null 2>&1; then
    PROXY_ONLINE=1
fi

# CSRF token
if [ -f "/proc/sys/kernel/random/uuid" ]; then
    CSRF_TOKEN="$(cat /proc/sys/kernel/random/uuid)"
elif command -v uuidgen >/dev/null 2>&1; then
    CSRF_TOKEN="$(uuidgen)"
else
    CSRF_TOKEN="patched-web-csrf-$(date +%s)"
fi

echo -e "🔌 Web server port:        ${BOLD}${PORT}${NC}"

if [ "$PROXY_ONLINE" -eq 1 ]; then
    echo -e "⚡ Model routing:          ${GREEN}agy-proxy (${PROXY_URL})${NC}"
    API_ARGS=(
        "--api_server_url" "$PROXY_URL"
        "--cloud_code_endpoint" "$PROXY_URL"
    )
else
    echo -e "⚠️  Model routing:          ${YELLOW}Google direct (agy-proxy is offline)${NC}"
    API_ARGS=(
        "--api_server_url" "https://generativelanguage.googleapis.com"
        "--cloud_code_endpoint" "https://daily-cloudcode-pa.googleapis.com"
    )
fi

URL="https://127.0.0.1:${PORT}/"

echo -e "\n${BOLD}🌐 Open in your browser:${NC}"
echo -e "${GREEN}${BOLD}👉 ${URL}${NC}\n"

# Background browser auto-open
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

LOG_FILE="${LOG_PATH:-${HOME}/.config/Antigravity/logs/language_server.log}"
mkdir -p "$(dirname "$LOG_FILE")"

FINAL_ARGS=(
    "--standalone"
    "--subclient_type" "hub"
    "--override_ide_name" "antigravity"
    "--override_ide_version" "2.23.0"
    "--override_user_agent_name" "antigravity"
    "--https_server_port" "$PORT"
    "--csrf_token" "$CSRF_TOKEN"
    "--app_data_dir" "antigravity"
    "--enable_sidecars"
    "${API_ARGS[@]}"
    "--web_bundle_path" "$BUNDLE_DIR"
)

if [ "$VERBOSE" -eq 1 ]; then
    echo -e "📄 Server logs:            ${YELLOW}Console (verbose output enabled)${NC}"
    echo -e "${YELLOW}ℹ️  Tip:${NC} If prompted with an SSL warning, click 'Advanced' -> 'Proceed to site'."
    echo -e "🛑 To stop the server: press ${BOLD}Ctrl + C${NC}"
    echo -e "${CYAN}================================================================${NC}\n"
    exec "$REAL_LS" "${FINAL_ARGS[@]}"
else
    echo -e "📄 Server logs:            ${CYAN}${LOG_FILE}${NC}"
    echo -e "${YELLOW}ℹ️  Tip:${NC} If prompted with an SSL warning, click 'Advanced' -> 'Proceed to site'."
    echo -e "🛑 To stop the server: press ${BOLD}Ctrl + C${NC}"
    echo -e "${CYAN}================================================================${NC}\n"
    exec "$REAL_LS" "${FINAL_ARGS[@]}" >> "$LOG_FILE" 2>&1
fi
