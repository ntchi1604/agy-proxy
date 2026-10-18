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
if [ "$FORCE_EXTRACT" -eq 1 ] || [ ! -d "$BUNDLE_DIR" ] || [ ! -f "$BUNDLE_DIR/main.js" ] || [ ! -f "$BUNDLE_DIR/index.html" ] || [ ! -f "$BUNDLE_DIR/.patched" ] || ! grep -q 'restrictToCorpDomain:!1' "$BUNDLE_DIR/main.js" 2>/dev/null || ! grep -q 'MODEL_ENUM_MAP' "$BUNDLE_DIR/main.js" 2>/dev/null || ! grep -q '_sep_ordered_v3' "$BUNDLE_DIR/main.js" 2>/dev/null || ! grep -q 'agy.selectedModelLabel' "$BUNDLE_DIR/main.js" 2>/dev/null; then
    NEEDS_EXTRACT=1
fi

if [ "$NEEDS_EXTRACT" -eq 1 ]; then
    echo -e "\n${YELLOW}⚙️  Extracting embedded Web UI zip and applying feature patches...${NC}"
    
    export REAL_LS
    export BUNDLE_DIR
    python3 - << 'EOF'
import sys, os, zipfile, io, struct, re

binary_path = os.environ["REAL_LS"]
out_dir = os.environ["BUNDLE_DIR"]
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

print("[*] Applying robust patches to main.js...")

# 1. Unlock Terminal domain restriction
js = re.sub(r'restrictToCorpDomain:!0', 'restrictToCorpDomain:!1', js)
js = re.sub(r'showCorpPasswordWarning:!0', 'showCorpPasswordWarning:!1', js)
js = re.sub(
    r'return\s+c\?\.restrictToCorpDomain&&typeof window!=="undefined"&&window\.location\.hostname!=="jetski\.corp\.google\.com"\?A\.createElement\(\w+,null\):A\.createElement\("div",\{"data-testid":"terminal-tab-surface"',
    'return A.createElement("div",{"data-testid":"terminal-tab-surface"',
    js
)

# 2. Disable Google3 Chat Migration warning card
js = re.sub(
    r'projectV5Migration:\{feature:\{enabled:!1,regroupCard:null\},applyFirst:\[\{runtimeGating:\{userCohort:\["google"\]\},feature:\w+\}\]\}',
    'projectV5Migration:{feature:{enabled:!1,regroupCard:null}}',
    js
)
js = re.sub(r'(\b\w+=\["App","Jetski Chat"),"Regroup Google3 Chats"(\])', r'\1\2', js)

# 3. Disable broken Agent Team blaze run script
js = re.sub(r'enabled:\w+\(\w+,"enable-agent-team"\)', 'enabled:void 0', js)

# 4. Robustness: Guard state/Zustand hooks against non-store arguments
m_hook = re.search(r'=\s*a\s*=>\s*(\w+)\(a\?\?(\w+),\{selector:\w+\}\)', js)
if m_hook:
    hook_fn = m_hook.group(1)
    dummy_store = m_hook.group(2)
    target_hook = f'var {hook_fn}=(a,b,...c)=>{{var e=b.selector,f=b.equalityFn'
    replacement_hook = f'var {hook_fn}=(a,b,...c)=>{{a=a&&typeof a.getState==="function"?a:{dummy_store};var e=b.selector,f=b.equalityFn'
    js = js.replace(target_hook, replacement_hook)
else:
    js = re.sub(
        r'var\s+(\w+)=\(a,b,\.\.\.c\)=>\{var e=b\.selector,f=b\.equalityFn',
        r'var \1=(a,b,...c)=>{a=a&&typeof a.getState==="function"?a:(typeof Bi!=="undefined"?Bi:Ai);var e=b.selector,f=b.equalityFn',
        js,
        count=1
    )

# 5. Remove broken Concierge / Chief of Staff archive
js = re.sub(r'conciergeAgent:\{label:"Chief of Staff",description:[^}]+settingKey:\w+\.CONCIERGE_AGENT_ENABLED,customFlag:"labs-concierge-agent",visibilityCustomFlag:"enable-concierge-agent"\},', '', js)
js = re.sub(r'conciergeAgent:\{feature:\{enabled:!1\},applyAll:\[.*?\}\]\}', 'conciergeAgent:{feature:{enabled:!1}}', js, flags=re.DOTALL)

# 6. Inject real proxied models and fix model selection
old_tk = r'var tk=a=>a\.modelOrAlias\?\{label:a\.label,value:a\.modelOrAlias\.choice\.case==="model"\?a\.modelOrAlias\.choice\.value:I\.Model\.UNSPECIFIED,modelAlias:a\.modelOrAlias\.choice\.case==="alias"\?a\.modelOrAlias\.choice\.value:void 0'
new_tk = r'var tk=a=>a.modelOrAlias?{label:a.label,value:a.value??(a.modelOrAlias.choice.case==="model"?a.modelOrAlias.choice.value:(typeof MODEL_ENUM_MAP!=="undefined"&&MODEL_ENUM_MAP[a.modelId||a.label]?MODEL_ENUM_MAP[a.modelId||a.label]:I.Model.UNSPECIFIED)),modelAlias:a.modelAlias||(a.modelOrAlias.choice.case==="alias"?a.modelOrAlias.choice.value:a.modelId)'
js = re.sub(old_tk, new_tk, js)

# 7. Render clean section headers in V3b (after hooks to preserve React Hook rules)
target_v3b_ret = 'return A.createElement(WM,{"data-testid":"model-selector-item"'
replacement_v3b_ret = 'if(t&&typeof a.label==="string"&&(a.label.startsWith("──")||a.label.includes("────"))){var cleanTitle=a.label.replace(/^[─\\s]+|[─\\s]+$/g,"");var icon=cleanTitle==="Default"?"★ ":(cleanTitle==="Web"?"✦ ":(cleanTitle==="Antigravity"?"⚡ ":""));return A.createElement("div",{key:a.label,className:"px-2 pt-2.5 pb-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider select-none flex items-center gap-2 opacity-85"},cleanTitle?A.createElement("span",{className:"shrink-0 font-medium flex items-center gap-1"},icon+cleanTitle):null,A.createElement("div",{className:"h-px flex-1 bg-border/60"}))}return A.createElement(WM,{"data-testid":"model-selector-item"'
js = js.replace(target_v3b_ret, replacement_v3b_ret, 1)

if '_agyEnhanced' not in js or '_sep_ordered_v3' not in js or 'agy.selectedModelLabel' not in js:
    p_ala = r'function\s+ALa\(\{children:a,userStatus:b,lastSelectedAgentModel:c,setLastSelectedAgentModel:e,supportsCustomModels:f,lastModelDefaultOverrideVersionId:g,setLastModelDefaultOverrideVersionId:h,customModelsState:k\}\)\{.*?\bensureConversationModelSeeded:G\}\),\[x,v,u,B,e,H,f,K,C,D,E,F,G\]\);return A\.createElement\(zLa\.Provider,\{value:g\},a\)\}'
    m_ala = re.search(p_ala, js, flags=re.DOTALL)
    if m_ala:
        patched_ala = '''var MODEL_ENUM_MAP={
"gemini-4-argon-web-high":1501,"gemini-4-argon-web-medium":1502,"gemini-4-argon-web-low":1503,"gemini-4-argon-web-task":1504,
"gemini-3.8-flash-web-high":1505,"gemini-3.8-flash-web-medium":1506,"gemini-3.8-flash-web-low":1507,"gemini-3.8-flash-web-task":1508,
"gemini-3.1-pro-web-high":1509,"gemini-3.1-pro-web-medium":1510,"gemini-3.1-pro-web-low":1511,
"gemini-3.5-flash-lite-web-high":1512,"gemini-3.5-flash-lite-web-medium":1513,"gemini-3.5-flash-lite-web-low":1514,
"claude-sonnet-5-5-high":1515,"claude-sonnet-5-5-medium":1516,"claude-sonnet-5-5-low":1517,
"claude-opus-5-5-high":1518,"claude-opus-5-5-medium":1519,"claude-opus-5-5-low":1520,
"claude-sonnet-4-6":1035,"claude-opus-4-6-thinking":1026,
"gemini-4-argon-high":1421,"gemini-4-argon-medium":1422,"gemini-4-argon-low":1423,"gemini-4-argon":1421,
"gemini-3.8-flash-high":1318,"gemini-3.8-flash-medium":1319,"gemini-3.8-flash-low":1320,
"gemini-3.8-flash-tiered":1521,"gemini-3.8-flash-deepagent":1522,
"gemini-3.7-flash-high":1315,"gemini-3.7-flash-medium":1316,"gemini-3.7-flash-low":1317,"gemini-3.7-flash-tiered":1523,
"gemini-3.6-flash-high":1524,"gemini-3.6-flash-medium":1525,"gemini-3.6-flash-low":1526,
"gemini-3-flash-agent":1527,"gemini-3.5-flash-low":1528,"gemini-3.5-flash-extra-low":1529,
"gemini-3.5-flash-lite":1530,"gemini-3.1-pro-high":1531,"gemini-3.1-pro-medium":1532,"gemini-3.1-pro-low":1533,
"gemini-3.1-flash-lite":1534,"gemini-3 Flash":1535,"gemini-3-flash":1535,"gemini-2.5-pro":1536,"gemini-2.5-flash":1537,
"gemini-2.5-flash-lite":1538,"gemini-2.5-flash-thinking":1539,"gpt-oss-120b-medium":1540
};
var __enhanceUserStatus=function(b){if(!b||!b.cascadeModelConfigData||b._agyEnhanced)return b;try{var d=b.cascadeModelConfigData,origConfigs=d.clientModelConfigs||[],origSorts=d.clientModelSorts||[],newConfigs=[...origConfigs],existingLabels=new Set(newConfigs.map(m=>m.label)),template=origConfigs.find(m=>!m.disabled)||origConfigs[0]||{},newSorts=JSON.parse(JSON.stringify(origSorts)),recGroup=newSorts.find(s=>s.name&&s.name.toLowerCase()==="recommended")?.groups?.[0];!recGroup&&newSorts.length>0&&newSorts[0].groups&&(recGroup=newSorts[0].groups[0]);var webModels=[{label:"Gemini 4 Argon (Web) (High)",alias:"gemini-4-argon-web-high"},{label:"Gemini 4 Argon (Web) (Medium)",alias:"gemini-4-argon-web-medium"},{label:"Gemini 4 Argon (Web) (Low)",alias:"gemini-4-argon-web-low"},{label:"Gemini 4 Argon (Web) (Agent)",alias:"gemini-4-argon-web-task"},{label:"Gemini 3.8 Flash (Web) (High)",alias:"gemini-3.8-flash-web-high"},{label:"Gemini 3.8 Flash (Web) (Medium)",alias:"gemini-3.8-flash-web-medium"},{label:"Gemini 3.8 Flash (Web) (Low)",alias:"gemini-3.8-flash-web-low"},{label:"Gemini 3.8 Flash (Web) (Agent)",alias:"gemini-3.8-flash-web-task"},{label:"Gemini 3.1 Pro (Web) (High)",alias:"gemini-3.1-pro-web-high"},{label:"Gemini 3.1 Pro (Web) (Medium)",alias:"gemini-3.1-pro-web-medium"},{label:"Gemini 3.1 Pro (Web) (Low)",alias:"gemini-3.1-pro-web-low"},{label:"Gemini 3.5 Flash-Lite (Web) (High)",alias:"gemini-3.5-flash-lite-web-high"},{label:"Gemini 3.5 Flash-Lite (Web) (Medium)",alias:"gemini-3.5-flash-lite-web-medium"},{label:"Gemini 3.5 Flash-Lite (Web) (Low)",alias:"gemini-3.5-flash-lite-web-low"}],agyModels=[{label:"Claude Sonnet 5.5 (High)",alias:"claude-sonnet-5-5-high"},{label:"Claude Sonnet 5.5 (Medium)",alias:"claude-sonnet-5-5-medium"},{label:"Claude Sonnet 5.5 (Low)",alias:"claude-sonnet-5-5-low"},{label:"Claude Opus 5.5 (High)",alias:"claude-opus-5-5-high"},{label:"Claude Opus 5.5 (Medium)",alias:"claude-opus-5-5-medium"},{label:"Claude Opus 5.5 (Low)",alias:"claude-opus-5-5-low"},{label:"Claude Sonnet 4.6 (Thinking)",alias:"claude-sonnet-4-6"},{label:"Claude Opus 4.6 (Thinking)",alias:"claude-opus-4-6-thinking"},{label:"Gemini 4 Argon (High)",alias:"gemini-4-argon-high"},{label:"Gemini 4 Argon (Medium)",alias:"gemini-4-argon-medium"},{label:"Gemini 4 Argon (Low)",alias:"gemini-4-argon-low"},{label:"Gemini 3.8 Flash (High)",alias:"gemini-3.8-flash-high"},{label:"Gemini 3.8 Flash (Medium)",alias:"gemini-3.8-flash-medium"},{label:"Gemini 3.8 Flash (Low)",alias:"gemini-3.8-flash-low"},{label:"Gemini 3.8 Flash (Tiered)",alias:"gemini-3.8-flash-tiered"},{label:"Gemini 3.8 Flash (DeepAgent)",alias:"gemini-3.8-flash-deepagent"},{label:"Gemini 3.7 Flash (High)",alias:"gemini-3.7-flash-high"},{label:"Gemini 3.7 Flash (Medium)",alias:"gemini-3.7-flash-medium"},{label:"Gemini 3.7 Flash (Low)",alias:"gemini-3.7-flash-low"},{label:"Gemini 3.7 Flash (Tiered)",alias:"gemini-3.7-flash-tiered"},{label:"Gemini 3.6 Flash (High)",alias:"gemini-3.6-flash-high"},{label:"Gemini 3.6 Flash (Medium)",alias:"gemini-3.6-flash-medium"},{label:"Gemini 3.6 Flash (Low)",alias:"gemini-3.6-flash-low"},{label:"Gemini 3.5 Flash (High)",alias:"gemini-3-flash-agent"},{label:"Gemini 3.5 Flash (Medium)",alias:"gemini-3.5-flash-low"},{label:"Gemini 3.5 Flash (Low)",alias:"gemini-3.5-flash-extra-low"},{label:"Gemini 3.5 Flash Lite",alias:"gemini-3.5-flash-lite"},{label:"Gemini 3.1 Pro (High)",alias:"gemini-3.1-pro-high"},{label:"Gemini 3.1 Pro (Medium)",alias:"gemini-3.1-pro-medium"},{label:"Gemini 3.1 Pro (Low)",alias:"gemini-3.1-pro-low"},{label:"Gemini 3.1 Flash Lite",alias:"gemini-3.1-flash-lite"},{label:"Gemini 3 Flash",alias:"gemini-3-flash"},{label:"Gemini 2.5 Pro",alias:"gemini-2.5-pro"},{label:"Gemini 2.5 Flash",alias:"gemini-2.5-flash"},{label:"Gemini 2.5 Flash Lite",alias:"gemini-2.5-flash-lite"},{label:"Gemini 2.5 Flash (Thinking)",alias:"gemini-2.5-flash-thinking"},{label:"GPT-OSS 120B",alias:"gpt-oss-120b-medium"}];var addSep=function(secLabel,secId){if(!existingLabels.has(secLabel)){var sepEntry=Object.assign({},template,{label:secLabel,disabled:!0,isRecommended:!1,modelId:secId,modelOrAlias:{"$typeName":"exa.codeium_common_pb.ModelOrAlias",choice:{case:"alias",value:secId}},supportedMimeTypes:{}});delete sepEntry.tagTitle;delete sepEntry.tagDescription;newConfigs.push(sepEntry);existingLabels.add(secLabel)}};addSep("── Default ──────────────────","sep_default");addSep("── Web ──────────────────","sep_web");addSep("── Antigravity ───────────","sep_agy");var addModels=function(items){for(var item of items){if(!existingLabels.has(item.label)){var enumVal=MODEL_ENUM_MAP[item.alias]||1500;var entry=Object.assign({},template,{label:item.label,disabled:!1,isRecommended:!0,modelId:item.alias,modelAlias:item.alias,value:enumVal,modelOrAlias:{"$typeName":"exa.codeium_common_pb.ModelOrAlias",choice:{case:"model",value:enumVal}},supportedMimeTypes:{}});delete entry.tagTitle;delete entry.tagDescription;newConfigs.push(entry);existingLabels.add(item.label)}}};addModels(webModels);addModels(agyModels);if(recGroup){var ordered=[];var origRecLabels=(recGroup&&Array.isArray(recGroup.modelLabels))?[...recGroup.modelLabels]:origConfigs.map(m=>m.label);var defaultLabels=[];origRecLabels.forEach(lbl=>{lbl&&!lbl.startsWith("──")&&!defaultLabels.includes(lbl)&&defaultLabels.push(lbl)});origConfigs.forEach(m=>{m.label&&!m.label.startsWith("──")&&!defaultLabels.includes(m.label)&&defaultLabels.push(m.label)});ordered.push("── Default ──────────────────");defaultLabels.forEach(lbl=>{!ordered.includes(lbl)&&ordered.push(lbl)});ordered.push("── Web ──────────────────");webModels.forEach(m=>{!ordered.includes(m.label)&&ordered.push(m.label)});ordered.push("── Antigravity ───────────");agyModels.forEach(m=>{!ordered.includes(m.label)&&ordered.push(m.label)});recGroup.modelLabels=ordered}return Object.assign({},b,{_agyEnhanced:!0,_sep_ordered_v3:!0,cascadeModelConfigData:Object.assign({},d,{clientModelConfigs:newConfigs,clientModelSorts:newSorts})})}catch(err){console.error("[AGY-Proxy] enhanceUserStatus failed:",err);return b}};
function ALa({children:a,userStatus:b,lastSelectedAgentModel:c,setLastSelectedAgentModel:e,supportsCustomModels:f,lastModelDefaultOverrideVersionId:g,setLastModelDefaultOverrideVersionId:h,customModelsState:k}){b=__enhanceUserStatus(b);var [_selLabel,_setSelLabel]=(0,A.useState)(()=>{try{return localStorage.getItem("agy.selectedModelLabel")||null}catch(E){return null}}),[l,m]=(0,A.useState)(null),[n,q]=(0,A.useState)({}),[r,t]=(0,A.useState)(void 0),u=(0,A.useMemo)(()=>{var J=xLa(k);for(let L of J)L.disabled=!f;return J},[k,f]),v=(0,A.useMemo)(()=>[...(b?.cascadeModelConfigData?.clientModelConfigs||[]).map(tk).filter(J=>J!==null).filter(J=>!J.disabled)],[b?.cascadeModelConfigData]),w=(0,A.useMemo)(()=>b?.cascadeModelConfigData?.defaultOverrideModelConfig,[b?.cascadeModelConfigData]);wLa(v,w,g,h,e);var x=(0,A.useMemo)(()=>{var J=b?.cascadeModelConfigData,L=J?.clientModelConfigs||[],M=J?.clientModelSorts||[];J=L.map(tk).filter(O=>O!==null).filter(O=>!O.disabled);L=wla(L,M);return L.length>0?L:vla(J)},[b?.cascadeModelConfigData]),y=(0,A.useCallback)((J,L)=>{if(v.length!==0||u.length!==0){if(L){let M=v.find(O=>O.label===L||O.modelAlias===L)||u.find(O=>O.label===L);if(M)return M}if(J===I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&u.length>0)return u[0];if(J!==void 0&&J!==I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&(J=uk(J,v)))return J;if(_selLabel){let M=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(M)return M}return v[0]??u.at(0)}},[v,u,_selLabel]),B=(0,A.useMemo)(()=>{if(v.length!==0||u.length!==0){if(_selLabel){let M=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(M)return M}return y(c,l)}},[y,c,v,u,l,_selLabel]),C=(0,A.useCallback)(J=>{if(J!==void 0&&(J=n[J],J!==void 0)){if(J.customLabel){let M=v.find(O=>O.label===J.customLabel||O.modelAlias===J.customLabel)||u.find(O=>O.label===J.customLabel);if(M)return M}return y(J.model,J.customLabel)}return B},[n,y,B,v,u]),D=(0,A.useCallback)((J,L,M,O,N)=>{J!==void 0&&q(P=>{var Q=P[J],R={model:L,customLabel:O,contextWindow:Gz(Q??r,L,N)};return Q?.model===L&&Q?.customLabel===O&&Q?.contextWindow===R.contextWindow?P:{...P,[J]:R}});if(M||J===void 0){e(L);t(P=>{var Q=Gz(P,L,N);return P?.model===L&&P?.contextWindow===Q?P:{model:L,contextWindow:Q}});m(O??null)}},[e,r]),E=(0,A.useCallback)((J,L,M,O)=>{var N=yLa(v,u,J);if(N){_setSelLabel(J);try{localStorage.setItem("agy.selectedModelLabel",J)}catch(err){}D(L,N.value,M,J,O)}else console.error(`[Model Select] Invalid model label: ${J}`)},[v,u,D]),F=(0,A.useCallback)(J=>(J=J===void 0?void 0:n[J])?J.contextWindow:Gz(r,B?.value),[n,r,B]),G=(0,A.useCallback)((J,L,M)=>{var O=Gz(r,L);q(N=>J in N?N:{...N,[J]:{model:L,customLabel:M,contextWindow:O}})},[r]),H=(0,A.useCallback)(J=>{E(J,void 0,!0)},[E]),K=(0,A.useMemo)(()=>b?.cascadeModelConfigData===void 0,[b?.cascadeModelConfigData]);g=(0,A.useMemo)(()=>({modelSorts:x,visibleModelConfigs:v,customModels:u,currentModelConfig:B,setLastSelectedAgentModel:e,setCurrentModelConfigByLabel:H,supportsCustomModels:f,isModelListLoading:K,getModelConfigForConversation:C,setModelForConversation:D,setModelConfigByLabelForConversation:E,getContextWindowForConversation:F,ensureConversationModelSeeded:G}),[x,v,u,B,e,H,f,K,C,D,E,F,G]);return A.createElement(zLa.Provider,{value:g},a)}'''
        js = js[:m_ala.start()] + patched_ala + js[m_ala.end():]

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

# 5. Write completion marker
with open(os.path.join(out_dir, '.patched'), 'w', encoding='utf-8') as f:
    f.write('patched=true\n')

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
