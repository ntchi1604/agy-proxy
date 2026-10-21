"""
Antigravity Web Mode Launcher.
Launches the official Antigravity language_server in standalone HTTPS Web mode,
bypassing the heavy Electron GUI process and freeing ~1.6 GB+ of RAM.
Automatically connects to agy-proxy for multi-account pooling and quota failover.
"""

import io
import logging
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agy_proxy.config import (
    get_configured_editor_path,
    get_configured_ls_path,
    set_configured_editor_path,
    set_configured_ls_path,
)

logger = logging.getLogger("agy_proxy.web_launcher")
console = Console()

DEFAULT_WEB_PORT = 44741
DEFAULT_PROXY_PORT = 8000
DEFAULT_PROXY_URL = f"http://127.0.0.1:{DEFAULT_PROXY_PORT}"
DEFAULT_IDE_VERSION = "2.25.0"
DEFAULT_BUNDLE_DIR = Path.home() / ".config" / "agy-proxy" / "web_ui"

KNOWN_CANDIDATE_DIRS = [
    # Linux (Desktop App & Hub)
    "/opt/Antigravity/resources/bin",
    "/opt/Antigravity",
    "/opt/antigravity/resources/bin",
    "/opt/antigravity",
    os.path.expanduser("~/.local/share/Antigravity/resources/bin"),
    os.path.expanduser("~/.local/share/Antigravity"),
    os.path.expanduser("~/.local/share/antigravity/resources/bin"),
    os.path.expanduser("~/.local/share/antigravity"),
    "/usr/lib/antigravity/resources/bin",
    "/usr/lib/antigravity",
    "/usr/share/antigravity",
    # Linux (Dedicated Antigravity IDE)
    "/opt/Antigravity IDE/resources/app/extensions/antigravity/bin",
    "/opt/Antigravity IDE",
    "/opt/antigravity-ide/resources/app/extensions/antigravity/bin",
    "/opt/antigravity-ide",
    os.path.expanduser("~/.local/share/Antigravity IDE/resources/app/extensions/antigravity/bin"),
    os.path.expanduser("~/.local/share/Antigravity IDE"),
    os.path.expanduser("~/Downloads/Antigravity IDE/Antigravity IDE/resources/app/extensions/antigravity/bin"),
    os.path.expanduser("~/Downloads/Antigravity IDE/Antigravity IDE"),
    os.path.expanduser("~/Downloads/Antigravity IDE"),
    os.path.expanduser("~/Downloads/Antigravity app"),
    # macOS (Desktop App & Hub)
    "/Applications/Antigravity.app/Contents/Resources/bin",
    "/Applications/Antigravity.app/Contents/Resources/app/resources/bin",
    "/Applications/Antigravity.app",
    os.path.expanduser("~/Applications/Antigravity.app/Contents/Resources/bin"),
    os.path.expanduser("~/Applications/Antigravity.app"),
    # macOS (Dedicated Antigravity IDE)
    "/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin",
    "/Applications/Antigravity IDE.app",
    os.path.expanduser("~/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin"),
    os.path.expanduser("~/Applications/Antigravity IDE.app"),
    # Windows (Desktop App & Hub)
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\resources\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity"),
    os.path.expandvars(r"%LOCALAPPDATA%\Antigravity\resources\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\Antigravity"),
    os.path.expandvars(r"%APPDATA%\Antigravity\resources\bin"),
    os.path.expandvars(r"%APPDATA%\Antigravity"),
    os.path.expandvars(r"%PROGRAMFILES%\Antigravity\resources\bin"),
    os.path.expandvars(r"%PROGRAMFILES%\Antigravity"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Antigravity\resources\bin"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Antigravity"),
    # Windows (Dedicated Antigravity IDE)
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity IDE\resources\app\extensions\antigravity\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity IDE"),
    os.path.expandvars(r"%LOCALAPPDATA%\Antigravity IDE\resources\app\extensions\antigravity\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\Antigravity IDE"),
    os.path.expandvars(r"%PROGRAMFILES%\Antigravity IDE\resources\app\extensions\antigravity\bin"),
    os.path.expandvars(r"%PROGRAMFILES%\Antigravity IDE"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Antigravity IDE\resources\app\extensions\antigravity\bin"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Antigravity IDE"),
]

KNOWN_BIN_NAMES = [
    # Universal / Desktop App (Linux & macOS)
    "language_server",
    # Windows Desktop App
    "language_server.exe",
    # Linux Dedicated IDE (x64, arm / arm64)
    "language_server_linux_x64",
    "language_server_linux_arm",
    "language_server_linux_arm64",
    # macOS Dedicated IDE (Apple Silicon & Intel)
    "language_server_macos_arm",
    "language_server_macos_x64",
    "language_server_darwin_arm64",
    "language_server_darwin_x64",
    # Windows Dedicated IDE (x64 & arm)
    "language_server_windows_x64.exe",
    "language_server_windows_arm.exe",
]

KNOWN_SUBPATHS = [
    "resources/bin",
    "resources/app/extensions/antigravity/bin",
    "Contents/Resources/bin",
    "Contents/Resources/app/resources/bin",
    "Contents/Resources/app/extensions/antigravity/bin",
    "Antigravity IDE/resources/app/extensions/antigravity/bin",
    "Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin",
    "Antigravity.app/Contents/Resources/bin",
    "bin",
]


def is_binary_executable(candidate: Path) -> bool:
    """Verifies that candidate path is a valid existing executable file."""
    if not candidate.is_file():
        return False
    if sys.platform == "win32":
        return candidate.suffix.lower() in (".exe", ".cmd", ".bat") or os.access(candidate, os.X_OK)
    return os.access(candidate, os.X_OK) or candidate.name.startswith("language_server")


def search_dir_for_language_server(directory: Path) -> Optional[Path]:
    """
    Searches an installation or editor directory for language_server binary.
    Checks direct filenames, known subpaths, and performs a bounded recursive search.
    """
    if not directory.is_dir():
        return None

    # 1. Direct match in directory
    for bname in KNOWN_BIN_NAMES:
        candidate = directory / bname
        if is_binary_executable(candidate):
            return candidate
        real = directory / f"{bname}.real"
        if is_binary_executable(real):
            return real

    # 2. Known subpaths within directory
    for sub in KNOWN_SUBPATHS:
        cand_sub = directory / sub
        if cand_sub.is_dir():
            for bname in KNOWN_BIN_NAMES:
                candidate = cand_sub / bname
                if is_binary_executable(candidate):
                    return candidate
                real = cand_sub / f"{bname}.real"
                if is_binary_executable(real):
                    return real

    # 3. Recursive search up to depth 6
    try:
        dir_depth = len(directory.resolve().parts)
        for root, dirs, files in os.walk(directory):
            cur_depth = len(Path(root).parts) - dir_depth
            if cur_depth > 6:
                dirs.clear()
                continue
            for f in files:
                fname = f[:-5] if f.endswith(".real") else f
                if fname in KNOWN_BIN_NAMES or (fname.startswith("language_server") and not fname.endswith((".log", ".txt", ".md", ".py", ".sh", ".json", ".yml", ".png"))):
                    candidate = Path(root) / f
                    if is_binary_executable(candidate):
                        return candidate
    except Exception as e:
        logger.debug(f"Error during recursive search in {directory}: {e}")

    return None


def find_language_server(
    custom_path: Optional[str | Path] = None,
    interactive: bool = False,
    persist: bool = True,
) -> Optional[Path]:
    """
    Locates the Antigravity language_server binary across platforms (Linux, macOS, Windows).
    Search hierarchy:
      1. Custom path (CLI argument / function param), file or directory
      2. Environment variables (ANTIGRAVITY_LS_PATH, ANTIGRAVITY_EDITOR_PATH, etc.)
      3. Persistent user config (~/.config/agy-proxy/config.json)
      4. Standard installation directories for the current OS
      5. PATH search
      6. Interactive prompt fallback (if interactive=True and running in TTY)
    """
    # 1. Custom path if explicitly provided
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        if p.is_file():
            if persist:
                try:
                    set_configured_ls_path(str(p))
                except Exception:
                    pass
            return p
        if p.is_dir():
            found = search_dir_for_language_server(p)
            if found:
                if persist:
                    try:
                        set_configured_editor_path(str(p))
                        set_configured_ls_path(str(found))
                    except Exception:
                        pass
                return found

    # 2. Environment variables
    for env_var in ("ANTIGRAVITY_LS_PATH", "ANTIGRAVITY_EDITOR_PATH", "ANTIGRAVITY_FILE", "ANTIGRAVITY_BIN_DIR", "ANTIGRAVITY_PATH"):
        env_val = os.environ.get(env_var)
        if env_val:
            p = Path(env_val).expanduser().resolve()
            if p.is_file():
                return p
            if p.is_dir():
                found = search_dir_for_language_server(p)
                if found:
                    return found

    # 3. Persistent user configuration
    try:
        cfg_ls = get_configured_ls_path()
        if cfg_ls:
            p_cfg = Path(cfg_ls).resolve()
            # If configured path is inside a temporary directory, prefer standard system install if present
            if any(part.startswith("tmp") for part in p_cfg.parts) or not p_cfg.is_file():
                for opt_path in ("/opt/Antigravity/resources/bin/language_server", "/opt/Antigravity IDE/resources/bin/language_server"):
                    opt_cand = Path(opt_path)
                    if opt_cand.is_file():
                        set_configured_ls_path(str(opt_cand))
                        return opt_cand
            if p_cfg.is_file():
                return p_cfg
        cfg_ed = get_configured_editor_path()
        if cfg_ed and Path(cfg_ed).is_dir():
            found = search_dir_for_language_server(Path(cfg_ed))
            if found:
                return found
    except Exception:
        pass

    # 4. Known directory locations
    for d_str in KNOWN_CANDIDATE_DIRS:
        if not d_str or "%" in d_str:
            continue
        try:
            d = Path(d_str).expanduser().resolve()
            if not d.exists():
                continue
            if d.is_file() and d.name.startswith("language_server"):
                return d
            if d.is_dir():
                found = search_dir_for_language_server(d)
                if found:
                    return found
        except Exception:
            continue

    # 5. PATH search
    for bname in ("language_server", "language_server.exe"):
        which_ls = shutil.which(bname)
        if which_ls:
            return Path(which_ls).resolve()

    # 6. Interactive fallback if running in an interactive terminal
    if interactive and sys.stdin and sys.stdin.isatty():
        console.print("[bold yellow]⚠️  Could not auto-detect Antigravity language_server path.[/bold yellow]")
        console.print("[dim]Antigravity may be installed in a custom location or not in standard system paths.[/dim]")
        try:
            user_input = input("Enter path to Antigravity directory or language_server binary: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if user_input:
            clean_input = user_input.strip("'\"")
            resolved = find_language_server(custom_path=clean_input, interactive=False, persist=persist)
            if resolved:
                console.print(f"[bold green]✓ Found and saved binary:[/bold green] [cyan]{resolved}[/cyan]")
                return resolved
            else:
                console.print(f"[bold red]❌ Could not locate valid language_server in:[/bold red] {clean_input}")

    return None


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a local TCP port is already open/listening."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_running_instances() -> Dict[str, Any]:
    """
    Inspects running system processes for:
    - Electron Antigravity GUI processes
    - Language server processes (identifying standalone web vs IDE mode)
    """
    my_pid = os.getpid()
    electron_pids: List[int] = []
    electron_details: List[Dict[str, Any]] = []
    ls_pids: List[int] = []
    ls_details: List[Dict[str, Any]] = []

    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = p.info.get("pid")
            if not pid or pid == my_pid:
                continue
            cmd = p.info.get("cmdline") or []
            cmd_str = " ".join(cmd)
            name = (p.info.get("name") or "").lower()

            # Ignore proxy itself
            if "agy_proxy" in cmd_str or "agy-proxy" in cmd_str or "test_web_launcher" in cmd_str:
                continue

            # Check for Electron Antigravity
            is_electron = False
            bin_name = os.path.basename(cmd[0]).lower() if cmd else ""
            if (
                name in ("antigravity", "antigravity-ide")
                or bin_name in ("antigravity", "antigravity-ide")
            ) and "language_server" not in cmd_str:
                is_electron = True
            elif (
                "/opt/antigravity/antigravity" in cmd_str.lower()
                or "/opt/antigravity ide/antigravity" in cmd_str.lower()
            ) and "language_server" not in cmd_str:
                is_electron = True

            if is_electron:
                electron_pids.append(pid)
                electron_details.append({"pid": pid, "cmd": cmd_str[:120]})
                continue

            # Check for language_server
            is_ls = (
                "language_server" in name
                or "language-server" in name
                or any("language_server" in os.path.basename(arg) for arg in cmd)
            )
            if is_ls:
                is_standalone = "--standalone" in cmd
                ls_pids.append(pid)
                ls_details.append({
                    "pid": pid,
                    "standalone": is_standalone,
                    "cmd": cmd_str[:160],
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    return {
        "electron_running": len(electron_pids) > 0,
        "electron_pids": electron_pids,
        "electron_details": electron_details,
        "language_server_running": len(ls_pids) > 0,
        "language_server_pids": ls_pids,
        "language_server_details": ls_details,
    }


def kill_electron_instances(force: bool = False) -> List[int]:
    """
    Terminates running Electron Antigravity GUI instances to free RAM and ports.
    Sends SIGTERM, then SIGKILL if still alive after timeout.
    """
    instances = get_running_instances()
    pids_to_kill = instances.get("electron_pids", [])
    killed_pids: List[int] = []

    for pid in pids_to_kill:
        try:
            p = psutil.Process(pid)
            p.terminate()
            killed_pids.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed_pids:
        # Wait up to 3 seconds for graceful exit
        time.sleep(1.0)
        for pid in killed_pids:
            try:
                p = psutil.Process(pid)
                if p.is_running():
                    p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return killed_pids


def kill_standalone_instances(port: Optional[int] = None) -> List[int]:
    """
    Terminates running standalone language_server instances to allow clean restart.
    Sends SIGTERM, then SIGKILL if still alive after timeout.
    """
    instances = get_running_instances()
    pids_to_kill: List[int] = []
    my_pid = os.getpid()

    for ls in instances.get("language_server_details", []):
        if ls.get("standalone"):
            pid = ls.get("pid")
            if pid and pid != my_pid and pid not in pids_to_kill:
                pids_to_kill.append(pid)

    # Also check if any process is listening on the specific web port
    if port:
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr and conn.laddr.port == port and conn.pid:
                    if conn.pid != my_pid and conn.pid not in pids_to_kill:
                        pids_to_kill.append(conn.pid)
        except Exception:
            pass

    killed_pids: List[int] = []
    for pid in pids_to_kill:
        try:
            p = psutil.Process(pid)
            p.terminate()
            killed_pids.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed_pids:
        time.sleep(0.8)
        for pid in killed_pids:
            try:
                p = psutil.Process(pid)
                if p.is_running():
                    p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(0.3)

    return killed_pids


def get_csrf_token() -> str:
    """Generates or retrieves a CSRF token for the language_server."""
    token = os.environ.get("CSRF_TOKEN")
    if token and len(token) > 8:
        return token

    # Check Linux kernel random UUID
    if os.path.exists("/proc/sys/kernel/random/uuid"):
        try:
            with open("/proc/sys/kernel/random/uuid", "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass

    return str(uuid.uuid4())


def check_proxy_alive(proxy_url: str = DEFAULT_PROXY_URL, timeout: float = 1.0) -> bool:
    """Checks if agy-proxy is reachable at the given URL."""
    try:
        import httpx
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{proxy_url.rstrip('/')}/health")
            if resp.status_code == 200:
                return True
            resp2 = client.get(f"{proxy_url.rstrip('/')}/api/info")
            return resp2.status_code == 200
    except Exception:
        # Fallback using urllib
        try:
            import urllib.request
            req = urllib.request.Request(f"{proxy_url.rstrip('/')}/health")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False


DEFAULT_GOOGLE_API_URL = "https://generativelanguage.googleapis.com"
DEFAULT_GOOGLE_CC_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com"


# ==============================================================================
# Web Hub Bundle Extraction & React Feature Patching
# ==============================================================================

def extract_web_bundle(binary_path: Path, out_dir: Path) -> bool:
    """
    Scans the language_server binary for the embedded Web UI zip archive and extracts it.
    """
    from agy_proxy.patcher import is_wrapper_script

    real_bin = binary_path
    if is_wrapper_script(binary_path):
        real_cand = binary_path.parent / f"{binary_path.name}.real"
        if real_cand.is_file():
            real_bin = real_cand

    if not real_bin.is_file():
        logger.error(f"Cannot extract web bundle: binary not found at {real_bin}")
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Scanning binary for embedded Web UI zip: {real_bin}")

    with open(real_bin, "rb") as f:
        data = f.read()

    eocd_sig = b"PK\x05\x06"
    pos = 0
    web_zip_data = None

    while True:
        idx = data.find(eocd_sig, pos)
        if idx == -1:
            break
        eocd_data = data[idx : idx + 22]
        if len(eocd_data) == 22:
            sig, disk1, disk2, count1, count2, cd_size, cd_offset = struct.unpack("<IHHHHII", eocd_data[:20])
            calc_start = idx - cd_size - cd_offset
            if 0 <= calc_start < idx:
                try:
                    candidate = data[calc_start : idx + 22]
                    z = zipfile.ZipFile(io.BytesIO(candidate))
                    names = z.namelist()
                    if "main.js" in names and "index.html" in names:
                        web_zip_data = candidate
                        logger.info(f"Found embedded Web UI zip ({len(names)} files)")
                        break
                except Exception:
                    pass
        pos = idx + 4

    if not web_zip_data:
        logger.error(f"Failed to locate Web UI zip archive inside {real_bin}")
        return False

    with zipfile.ZipFile(io.BytesIO(web_zip_data)) as z:
        z.extractall(out_dir)

    return True


def patch_web_bundle(bundle_dir: Path) -> bool:
    """
    Applies non-destructive feature patches to extracted Web UI assets:
    - Unlocks Terminal domain restriction (allows Jetbox Terminal on local/custom hosts)
    - Fixes and expands model selection menus with grouped categories
    - Unlocks developer features, Thought Editing, Split View, Battle Mode, Autonomous Mode
    - Disables broken Google3 Piper/blaze dependencies
    """
    main_js_path = bundle_dir / "main.js"
    index_html_path = bundle_dir / "index.html"

    if not main_js_path.is_file() or not index_html_path.is_file():
        logger.error(f"main.js or index.html missing in {bundle_dir}")
        return False

    # 1. Patch main.js
    with open(main_js_path, "r", encoding="utf-8") as f:
        js = f.read()

    # 1.1 Unlock Terminal domain restriction
    js = re.sub(r"restrictToCorpDomain:!0", "restrictToCorpDomain:!1", js)
    js = re.sub(r"showCorpPasswordWarning:!0", "showCorpPasswordWarning:!1", js)
    js = re.sub(
        r'return\s+c\?\.restrictToCorpDomain&&typeof window!=="undefined"&&window\.location\.hostname!=="jetski\.corp\.google\.com"\?A\.createElement\(\w+,null\):A\.createElement\("div",\{"data-testid":"terminal-tab-surface"',
        'return A.createElement("div",{"data-testid":"terminal-tab-surface"',
        js,
    )

    # 1.2 Disable Google3 Chat Migration warning card
    js = re.sub(
        r'projectV5Migration:\{feature:\{enabled:!1,regroupCard:null\},applyFirst:\[\{runtimeGating:\{userCohort:\["google"\]\},feature:\w+\}\]\}',
        "projectV5Migration:{feature:{enabled:!1,regroupCard:null}}",
        js,
    )
    js = re.sub(r'(\b\w+=\["App","Jetski Chat"),"Regroup Google3 Chats"(\])', r"\1\2", js)

    # 1.3 Disable broken Agent Team blaze run script
    js = re.sub(r'enabled:\w+\(\w+,"enable-agent-team"\)', "enabled:void 0", js)

    # 1.4 Guard state/Zustand hooks against non-store arguments
    m_hook = re.search(r"=\s*a\s*=>\s*(\w+)\(a\?\?(\w+),\{selector:\w+\}\)", js)
    if m_hook:
        hook_fn = m_hook.group(1)
        dummy_store = m_hook.group(2)
        target_hook = f"var {hook_fn}=(a,b,...c)=>{{var e=b.selector,f=b.equalityFn"
        replacement_hook = f"var {hook_fn}=(a,b,...c)=>{{a=a&&typeof a.getState===\"function\"?a:{dummy_store};var e=b.selector,f=b.equalityFn"
        js = js.replace(target_hook, replacement_hook)
    else:
        js = re.sub(
            r"var\s+(\w+)=\(a,b,\.\.\.c\)=>\{var e=b\.selector,f=b\.equalityFn",
            r"var \1=(a,b,...c)=>{a=a&&typeof a.getState===\"function\"?a:(typeof Bi!==\"undefined\"?Bi:Ai);var e=b.selector,f=b.equalityFn",
            js,
            count=1,
        )

    # 1.5 Remove broken Concierge / Chief of Staff archive
    js = re.sub(
        r'conciergeAgent:\{label:"Chief of Staff",description:[^}]+settingKey:\w+\.CONCIERGE_AGENT_ENABLED,customFlag:"labs-concierge-agent",visibilityCustomFlag:"enable-concierge-agent"\},',
        "",
        js,
    )
    js = re.sub(
        r"conciergeAgent:\{feature:\{enabled:!1\},applyAll:\[.*?\}\]\}",
        "conciergeAgent:{feature:{enabled:!1}}",
        js,
        flags=re.DOTALL,
    )

    # 1.6 Inject real proxied models and fix model selection (dynamic converter matching with static fallback)
    converter_pat = re.compile(
        r'var\s+([A-Za-z0-9_$]+)\s*=\s*([A-Za-z0-9_$]+)\s*=>\s*\2\.modelOrAlias\?\{label:\s*\2\.label,\s*value:\s*\2\.modelOrAlias\.choice\.case\s*===\s*"model"\?\s*\2\.modelOrAlias\.choice\.value:\s*([A-Za-z0-9_$]+)\.Model\.UNSPECIFIED,\s*modelAlias:\s*\2\.modelOrAlias\.choice\.case\s*===\s*"alias"\?\s*\2\.modelOrAlias\.choice\.value:\s*void 0'
    )
    converter_repl = (
        r'var \g<1>=\g<2>=>\g<2>.modelOrAlias?{label:\g<2>.label,value:\g<2>.value??(\g<2>.modelOrAlias.choice.case==="model"?\g<2>.modelOrAlias.choice.value:(typeof MODEL_ENUM_MAP!=="undefined"&&MODEL_ENUM_MAP[\g<2>.modelId||\g<2>.label]?MODEL_ENUM_MAP[\g<2>.modelId||\g<2>.label]:\g<3>.Model.UNSPECIFIED)),modelAlias:\g<2>.modelOrAlias.choice.case==="alias"?\g<2>.modelOrAlias.choice.value:void 0'
    )
    js, conv_count = converter_pat.subn(converter_repl, js)
    if conv_count == 0:
        # Fallback to static tk/Ck pattern
        old_tk_pat = r'var\s+(tk|Ck)=a=>a\.modelOrAlias\?\{label:a\.label,value:a\.modelOrAlias\.choice\.case==="model"\?a\.modelOrAlias\.choice\.value:I\.Model\.UNSPECIFIED,modelAlias:a\.modelOrAlias\.choice\.case==="alias"\?a\.modelOrAlias\.choice\.value:void 0'
        new_tk_repl = r'var \1=a=>a.modelOrAlias?{label:a.label,value:a.value??(a.modelOrAlias.choice.case==="model"?a.modelOrAlias.choice.value:(typeof MODEL_ENUM_MAP!=="undefined"&&MODEL_ENUM_MAP[a.modelId||a.label]?MODEL_ENUM_MAP[a.modelId||a.label]:I.Model.UNSPECIFIED)),modelAlias:a.modelOrAlias.choice.case==="alias"?a.modelOrAlias.choice.value:void 0'
        js = re.sub(old_tk_pat, new_tk_repl, js)

    # Fallback: guarantee planModel in WX hook is never void 0 if enum value (r) is present
    js = js.replace('planModel:w.choice?.case==="model"?w.choice.value:void 0', 'planModel:(w.choice?.case==="model"?w.choice.value:void 0)??r')

    # 1.7 Render clean section headers in V3b (dynamic item renderer discovery with zM/WM fallback)
    item_pat = re.compile(r'return\s+([A-Za-z0-9_$]+)\.createElement\(([A-Za-z0-9_$]+),\{(?:\s*"data-testid"\s*:\s*"model-selector-item")')
    m_item = item_pat.search(js)
    if m_item:
        react_id = m_item.group(1)
        item_comp = m_item.group(2)
        replacement_v3b_ret = (
            f'if(t&&typeof a.label==="string"&&(a.label.startsWith("──")||a.label.includes("────"))){{'
            f'var cleanTitle=a.label.replace(/^[─\\s]+|[─\\s]+$/g,"");'
            f'var icon=cleanTitle==="Default"?"★ ":(cleanTitle==="Web"?"✦ ":(cleanTitle==="Antigravity"?"⚡ ":""));'
            f'return {react_id}.createElement("div",{{key:a.label,className:"px-2 pt-2.5 pb-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider select-none flex items-center gap-2 opacity-85"}},'
            f'cleanTitle?{react_id}.createElement("span",{{className:"shrink-0 font-medium flex items-center gap-1"}},icon+cleanTitle):null,'
            f'{react_id}.createElement("div",{{className:"h-px flex-1 bg-border/60"}}))}}'
            f'return {react_id}.createElement({item_comp},{{"data-testid":"model-selector-item"'
        )
        js = js[:m_item.start()] + replacement_v3b_ret + js[m_item.end():]
    else:
        for item_comp in ["zM", "WM"]:
            target_v3b_ret = f'return A.createElement({item_comp},{{"data-testid":"model-selector-item"'
            replacement_v3b_ret = f'if(t&&typeof a.label==="string"&&(a.label.startsWith("──")||a.label.includes("────"))){{var cleanTitle=a.label.replace(/^[─\\s]+|[─\\s]+$/g,"");var icon=cleanTitle==="Default"?"★ ":(cleanTitle==="Web"?"✦ ":(cleanTitle==="Antigravity"?"⚡ ":""));return A.createElement("div",{{key:a.label,className:"px-2 pt-2.5 pb-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider select-none flex items-center gap-2 opacity-85"}},cleanTitle?A.createElement("span",{{className:"shrink-0 font-medium flex items-center gap-1"}},icon+cleanTitle):null,A.createElement("div",{{className:"h-px flex-1 bg-border/60"}}))}}return A.createElement({item_comp},{{"data-testid":"model-selector-item"'
            if target_v3b_ret in js:
                js = js.replace(target_v3b_ret, replacement_v3b_ret, 1)
                break

    # 1.8 Inject Model Enum Map, __enhanceUserStatus and state provider (dynamic structural matching + static fallback)
    if "_agyEnhanced" not in js or "_sep_ordered_v8" not in js or "agy.selectedModelLabel" not in js:
        enhancer_common = '''var MODEL_ENUM_MAP={
"gemini-3.8-flash-high":1318,"gemini-3.8-flash-medium":1319,"gemini-3.8-flash-low":1320,"gemini-3.8-flash-tiered":1322,"gemini-3.8-flash-deepagent":1522,
"gemini-3.7-flash-high":1318,"gemini-3.7-flash-medium":1319,"gemini-3.7-flash-low":1320,"gemini-3.7-flash-tiered":1322,
"gemini-3.6-flash-high":1318,"gemini-3.6-flash-medium":1319,"gemini-3.6-flash-low":1320,
"gemini-3-flash-agent":1084,"gemini-3.5-flash-low":1020,"gemini-3.5-flash-extra-low":1187,
"gemini-3.5-flash-lite":1198,"gemini-3.1-pro-high":246,"gemini-3.1-pro-medium":246,"gemini-3.1-pro-low":246,
"gemini-3.1-flash-lite":1050,"gemini-3 Flash":1018,"gemini-3-flash":1018,"gemini-2.5-pro":246,"gemini-2.5-flash":312,
"gemini-2.5-flash-lite":330,"gemini-2.5-flash-thinking":313,"gpt-oss-120b-medium":342,
"claude-sonnet-4-6":1035,"claude-opus-4-6-thinking":1026,
"claude-sonnet-5-5-high":1515,"claude-sonnet-5-5-medium":1516,"claude-sonnet-5-5-low":1517,
"claude-opus-5-5-high":1518,"claude-opus-5-5-medium":1519,"claude-opus-5-5-low":1520,
"gemini-4-argon-web-high":1501,"gemini-4-argon-web-medium":1502,"gemini-4-argon-web-low":1503,"gemini-4-argon-web-task":1504,
"gemini-3.8-flash-web-high":1505,"gemini-3.8-flash-web-medium":1506,"gemini-3.8-flash-web-low":1507,"gemini-3.8-flash-web-task":1508,
"gemini-3.1-pro-web-high":1509,"gemini-3.1-pro-web-medium":1510,"gemini-3.1-pro-web-low":1511,
"gemini-3.5-flash-lite-web-high":1512,"gemini-3.5-flash-lite-web-medium":1513,"gemini-3.5-flash-lite-web-low":1514,
"gemini-3.1-flash-image":1021,"gemini-3-pro-image":1022,"gemini-2.5-flash-image":314
};
var __enhanceUserStatus=function(b){if(!b||!b.cascadeModelConfigData||b._agyEnhanced)return b;try{var isProxyActive=false;try{if(typeof window!=="undefined"&&window.__AGY_PROXY_ACTIVE__!==undefined){isProxyActive=Boolean(window.__AGY_PROXY_ACTIVE__)}else if(typeof localStorage!=="undefined"&&localStorage.getItem("agy.proxyActive")!==null){isProxyActive=localStorage.getItem("agy.proxyActive")==="true"}}catch(e){}var d=b.cascadeModelConfigData,origConfigs=d.clientModelConfigs||[],origSorts=d.clientModelSorts||[],newConfigs=[...origConfigs],existingLabels=new Set(newConfigs.map(m=>m.label)),template=origConfigs.find(m=>!m.disabled)||origConfigs[0]||{},newSorts=JSON.parse(JSON.stringify(origSorts)),recGroup=newSorts.find(s=>s.name&&s.name.toLowerCase()==="recommended")?.groups?.[0];!recGroup&&newSorts.length>0&&newSorts[0].groups&&(recGroup=newSorts[0].groups[0]);var webModels=[{label:"Gemini 4 Argon (Web) (High)",alias:"gemini-4-argon-web-high"},{label:"Gemini 4 Argon (Web) (Medium)",alias:"gemini-4-argon-web-medium"},{label:"Gemini 4 Argon (Web) (Low)",alias:"gemini-4-argon-web-low"},{label:"Gemini 4 Argon (Web) (Agent)",alias:"gemini-4-argon-web-task"},{label:"Gemini 3.8 Flash (Web) (High)",alias:"gemini-3.8-flash-web-high"},{label:"Gemini 3.8 Flash (Web) (Medium)",alias:"gemini-3.8-flash-web-medium"},{label:"Gemini 3.8 Flash (Web) (Low)",alias:"gemini-3.8-flash-web-low"},{label:"Gemini 3.8 Flash (Web) (Agent)",alias:"gemini-3.8-flash-web-task"},{label:"Gemini 3.1 Pro (Web) (High)",alias:"gemini-3.1-pro-web-high"},{label:"Gemini 3.1 Pro (Web) (Medium)",alias:"gemini-3.1-pro-web-medium"},{label:"Gemini 3.1 Pro (Web) (Low)",alias:"gemini-3.1-pro-web-low"},{label:"Gemini 3.5 Flash-Lite (Web) (High)",alias:"gemini-3.5-flash-lite-web-high"},{label:"Gemini 3.5 Flash-Lite (Web) (Medium)",alias:"gemini-3.5-flash-lite-web-medium"},{label:"Gemini 3.5 Flash-Lite (Web) (Low)",alias:"gemini-3.5-flash-lite-web-low"}],agyModels=[{label:"Gemini 3.8 Flash (High)",alias:"gemini-3.8-flash-high"},{label:"Gemini 3.8 Flash (Medium)",alias:"gemini-3.8-flash-medium"},{label:"Gemini 3.8 Flash (Low)",alias:"gemini-3.8-flash-low"},{label:"Gemini 3.8 Flash (Tiered)",alias:"gemini-3.8-flash-tiered"},{label:"Claude Sonnet 4.6 (Thinking)",alias:"claude-sonnet-4-6"},{label:"Claude Opus 4.6 (Thinking)",alias:"claude-opus-4-6-thinking"},{label:"GPT-OSS 120B",alias:"gpt-oss-120b-medium"},{label:"Gemini 3.5 Flash (High)",alias:"gemini-3-flash-agent"},{label:"Gemini 3.5 Flash (Medium)",alias:"gemini-3.5-flash-low"},{label:"Gemini 3.5 Flash (Low)",alias:"gemini-3.5-flash-extra-low"},{label:"Gemini 3.5 Flash Lite",alias:"gemini-3.5-flash-lite"},{label:"Gemini 3.1 Flash Lite",alias:"gemini-3.1-flash-lite"},{label:"Gemini 3.1 Flash (Image)",alias:"gemini-3.1-flash-image"},{label:"Gemini 3 Flash",alias:"gemini-3-flash"},{label:"Gemini 2.5 Pro",alias:"gemini-2.5-pro"},{label:"Gemini 2.5 Flash",alias:"gemini-2.5-flash"},{label:"Gemini 2.5 Flash Lite",alias:"gemini-2.5-flash-lite"},{label:"Gemini 2.5 Flash (Thinking)",alias:"gemini-2.5-flash-thinking"}];if(isProxyActive){agyModels.push({label:"Gemini 3.8 Flash (DeepAgent)",alias:"gemini-3.8-flash-deepagent"},{label:"Claude Sonnet 5.5 (High)",alias:"claude-sonnet-5-5-high"},{label:"Claude Opus 5.5 (High)",alias:"claude-opus-5-5-high"})};var addSep=function(secLabel,secId){if(!existingLabels.has(secLabel)){var sepEntry=Object.assign({},template,{label:secLabel,disabled:!0,isRecommended:!1,modelId:secId,modelOrAlias:{"$typeName":"exa.codeium_common_pb.ModelOrAlias",choice:{case:"alias",value:secId}},supportedMimeTypes:{}});delete sepEntry.tagTitle;delete sepEntry.tagDescription;newConfigs.push(sepEntry);existingLabels.add(secLabel)}};var addModels=function(items){for(var item of items){if(!existingLabels.has(item.label)){var enumVal=MODEL_ENUM_MAP[item.alias]||1500;var entry=Object.assign({},template,{label:item.label,disabled:!1,isRecommended:!0,modelId:item.alias,value:enumVal,modelOrAlias:{"$typeName":"exa.codeium_common_pb.ModelOrAlias",choice:{case:"model",value:enumVal}},supportedMimeTypes:{}});delete entry.modelAlias;delete entry.tagTitle;delete entry.tagDescription;newConfigs.push(entry);existingLabels.add(item.label)}}};addSep("── Default ──────────────────","sep_default");if(isProxyActive){addSep("── Web ──────────────────","sep_web");addModels(webModels)};addSep("── Antigravity ───────────","sep_agy");addModels(agyModels);if(recGroup){var ordered=[];var origRecLabels=(recGroup&&Array.isArray(recGroup.modelLabels))?[...recGroup.modelLabels]:origConfigs.map(m=>m.label);var defaultLabels=[];origRecLabels.forEach(lbl=>{lbl&&!lbl.startsWith("──")&&!defaultLabels.includes(lbl)&&defaultLabels.push(lbl)});origConfigs.forEach(m=>{m.label&&!m.label.startsWith("──")&&!defaultLabels.includes(m.label)&&defaultLabels.push(m.label)});ordered.push("── Default ──────────────────");defaultLabels.forEach(lbl=>{!ordered.includes(lbl)&&ordered.push(lbl)});if(isProxyActive){ordered.push("── Web ──────────────────");webModels.forEach(m=>{!ordered.includes(m.label)&&ordered.push(m.label)})};ordered.push("── Antigravity ───────────");agyModels.forEach(m=>{!ordered.includes(m.label)&&ordered.push(m.label)});recGroup.modelLabels=ordered}return Object.assign({},b,{_agyEnhanced:!0,_sep_ordered_v8:!0,_proxyActive:isProxyActive,cascadeModelConfigData:Object.assign({},d,{clientModelConfigs:newConfigs,clientModelSorts:newSorts})})}catch(err){console.error("[AGY-Proxy] enhanceUserStatus failed:",err);return b}};
'''
        # Dynamic structural matching for React State Provider
        prov_re = re.compile(
            r"function\s+([A-Za-z0-9_$]+)\(\{\s*"
            r"children:\s*([A-Za-z0-9_$]+),\s*"
            r"userStatus:\s*([A-Za-z0-9_$]+)"
            r"(?:,\s*lastSelectedAgentModel:\s*([A-Za-z0-9_$]+))?"
            r"(?:,\s*setLastSelectedAgentModel:\s*([A-Za-z0-9_$]+))?"
            r"(?:,\s*supportsCustomModels:\s*([A-Za-z0-9_$]+))?"
            r"(?:,\s*lastModelDefaultOverrideVersionId:\s*([A-Za-z0-9_$]+))?"
            r"(?:,\s*setLastModelDefaultOverrideVersionId:\s*([A-Za-z0-9_$]+))?"
            r"(?:,\s*customModelsState:\s*([A-Za-z0-9_$]+))?"
            r"[^)]*\}\)\{"
        )
        m_prov = prov_re.search(js)
        applied_provider_patch = False

        if m_prov:
            fn_name = m_prov.group(1)
            p_custom_models = m_prov.group(9) or "k"
            p_override_v_id = m_prov.group(7) or "g"
            p_set_override_v_id = m_prov.group(8) or "h"
            p_set_last_model = m_prov.group(5) or "e"

            start_idx = m_prov.start()
            end_pat = re.compile(r"(?:return\s+([A-Za-z0-9_$]+)\.createElement\(([A-Za-z0-9_$]+))?\.Provider,\{value:\s*([A-Za-z0-9_$]+)\},\s*([A-Za-z0-9_$]+)\)\}")
            end_m = end_pat.search(js[start_idx:start_idx+6000])
            end_idx = -1
            react_var = "A"
            provider_ctx = "fMa" if fn_name == "gMa" else "zLa"

            if end_m:
                end_idx = start_idx + end_m.end()
                if end_m.group(1):
                    react_var = end_m.group(1)
                if end_m.group(2):
                    provider_ctx = end_m.group(2)
            else:
                pos = js.find(".Provider,{value:g},a)}", start_idx)
                if pos != -1:
                    end_idx = pos + len(".Provider,{value:g},a)}")

            if end_idx != -1:
                full_fn_body = js[start_idx:end_idx]
                m_custom = re.search(r"([A-Za-z0-9_$]+)\(" + p_custom_models + r"\)", full_fn_body)
                m_conv = re.search(r"\.map\(([A-Za-z0-9_$]+)\)\.filter", full_fn_body)
                m_override = re.search(r"([A-Za-z0-9_$]+)\([A-Za-z0-9_$]+,\s*[A-Za-z0-9_$]+,\s*" + p_override_v_id + r",\s*" + p_set_override_v_id + r",\s*" + p_set_last_model + r"\)", full_fn_body)
                m_sort = re.search(r"=([A-Za-z0-9_$]+)\([A-Za-z0-9_$]+,\s*[A-Za-z0-9_$]+\);return\s+[A-Za-z0-9_$]+\.length>0\?[A-Za-z0-9_$]+:([A-Za-z0-9_$]+)\([A-Za-z0-9_$]+\)", full_fn_body)
                m_find = re.search(r"Model\.GOOGLE_GEMINI_INTERNAL_BYOM&&\([A-Za-z0-9_$]+=([A-Za-z0-9_$]+)\([A-Za-z0-9_$]+,\s*[A-Za-z0-9_$]+\)\)", full_fn_body)
                m_ctx_w = re.search(r"contextWindow:([A-Za-z0-9_$]+)\(", full_fn_body)
                m_lbl = re.search(r"([A-Za-z0-9_$]+)\([A-Za-z0-9_$]+,\s*[A-Za-z0-9_$]+,\s*[A-Za-z0-9_$]+\);if\([A-Za-z0-9_$]+\)\{", full_fn_body)

                custom_models_fn = m_custom.group(1) if m_custom else ("dMa" if fn_name == "gMa" else "xLa")
                converter_fn = m_conv.group(1) if m_conv else ("Ck" if fn_name == "gMa" else "tk")
                override_fn = m_override.group(1) if m_override else ("cMa" if fn_name == "gMa" else "wLa")
                sort1_fn = m_sort.group(1) if m_sort else ("dma" if fn_name == "gMa" else "wla")
                sort2_fn = m_sort.group(2) if m_sort else ("cma" if fn_name == "gMa" else "vla")
                find_model_fn = m_find.group(1) if m_find else ("Dk" if fn_name == "gMa" else "uk")
                ctx_w_fn = m_ctx_w.group(1) if m_ctx_w else ("Cz" if fn_name == "gMa" else "Gz")
                label_resolve_fn = m_lbl.group(1) if m_lbl else ("eMa" if fn_name == "gMa" else "yLa")

                body = (
                    f'function {fn_name}({{children:a,userStatus:b,lastSelectedAgentModel:c,setLastSelectedAgentModel:e,supportsCustomModels:f,lastModelDefaultOverrideVersionId:g,setLastModelDefaultOverrideVersionId:h,customModelsState:k}}){{'
                    f'b=__enhanceUserStatus(b);'
                    f'var [_selLabel,_setSelLabel]=(0,{react_var}.useState)(()=>{{try{{return localStorage.getItem("agy.selectedModelLabel")||null}}catch(E){{return null}}}}),'
                    f'[l,m]=(0,{react_var}.useState)(null),[n,q]=(0,{react_var}.useState)({{}}),[r,t]=(0,{react_var}.useState)(void 0),'
                    f'u=(0,{react_var}.useMemo)(()=>{{var J={custom_models_fn}(k);for(let L of J)L.disabled=!f;return J}},[k,f]),'
                    f'v=(0,{react_var}.useMemo)(()=>[...(b?.cascadeModelConfigData?.clientModelConfigs||[]).map({converter_fn}).filter(J=>J!==null).filter(J=>!J.disabled)],[b?.cascadeModelConfigData]),'
                    f'w=(0,{react_var}.useMemo)(()=>b?.cascadeModelConfigData?.defaultOverrideModelConfig,[b?.cascadeModelConfigData]);'
                    f'{override_fn}(v,w,g,h,e);'
                    f'var x=(0,{react_var}.useMemo)(()=>{{var J=b?.cascadeModelConfigData,L=J?.clientModelConfigs||[],N=J?.clientModelSorts||[];J=L.map({converter_fn}).filter(O=>O!==null).filter(O=>!O.disabled);L={sort1_fn}(L,N);return L.length>0?L:{sort2_fn}(J)}},[b?.cascadeModelConfigData]),'
                    f'y=(0,{react_var}.useCallback)((J,L)=>{{if(v.length!==0||u.length!==0){{if(L){{let N=v.find(O=>O.label===L||O.modelAlias===L)||u.find(O=>O.label===L);if(N)return N}}if(J===I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&u.length>0)return u[0];if(J!==void 0&&J!==I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&(J={find_model_fn}(J,v)))return J;if(_selLabel){{let N=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(N)return N}}return v[0]??u.at(0)}}}},[v,u,_selLabel]),'
                    f'B=(0,{react_var}.useMemo)(()=>{{if(v.length!==0||u.length!==0){{if(_selLabel){{let N=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(N)return N}}return y(c,l)}}}},[y,c,v,u,l,_selLabel]),'
                    f'C=(0,{react_var}.useCallback)(J=>{{if(J!==void 0&&(J=n[J],J!==void 0)){{if(J.customLabel){{let N=v.find(O=>O.label===J.customLabel||O.modelAlias===J.customLabel)||u.find(O=>O.label===J.customLabel);if(N)return N}}return y(J.model,J.customLabel)}}return B}},[n,y,B,v,u]),'
                    f'D=(0,{react_var}.useCallback)((J,L,N,O,M)=>{{J!==void 0&&q(Q=>{{var P=Q[J],R={{model:L,customLabel:O,contextWindow:{ctx_w_fn}(P??r,L,M)}};return P?.model===L&&P?.customLabel===O&&P?.contextWindow===R.contextWindow?Q:{{...Q,[J]:R}}}});if(N||J===void 0)e(L),t(Q=>{{var P={ctx_w_fn}(Q,L,M);return Q?.model===L&&Q?.contextWindow===P?Q:{{model:L,contextWindow:P}}}}),m(O??null)}},[e,r]),'
                    f'E=(0,{react_var}.useCallback)((J,L,N,O)=>{{var M={label_resolve_fn}(v,u,J);if(M){{_setSelLabel(J);try{{localStorage.setItem("agy.selectedModelLabel",J)}}catch(err){{}}var Q=u.some(P=>P.label===J);D(L,M.value,N,Q?J:O,O)}}else console.error(`[Model Select] Invalid model label: ${{J}}`)}},[v,u,D]),'
                    f'G=(0,{react_var}.useCallback)(J=>(J=J===void 0?void 0:n[J])?J.contextWindow:{ctx_w_fn}(r,B?.value),[n,r,B]),'
                    f'F=(0,{react_var}.useCallback)((J,L,N)=>{{var O={ctx_w_fn}(r,L);q(M=>J in M?M:{{...M,[J]:{{model:L,customLabel:N,contextWindow:O}}}})}},[r]),'
                    f'H=(0,{react_var}.useCallback)(J=>{{E(J,void 0,!0)}},[E]),'
                    f'K=(0,{react_var}.useMemo)(()=>b?.cascadeModelConfigData===void 0,[b?.cascadeModelConfigData]);'
                    f'g=(0,{react_var}.useMemo)(()=>({{modelSorts:x,visibleModelConfigs:v,customModels:u,currentModelConfig:B,setLastSelectedAgentModel:e,setCurrentModelConfigByLabel:H,supportsCustomModels:f,isModelListLoading:K,getModelConfigForConversation:C,setModelForConversation:D,setModelConfigByLabelForConversation:E,getContextWindowForConversation:G,ensureConversationModelSeeded:F}}),[x,v,u,B,e,H,f,K,C,D,E,G,F]);'
                    f'return {react_var}.createElement({provider_ctx}.Provider,{{value:g}},a)}}'
                )
                js = js[:start_idx] + enhancer_common + body + js[end_idx:]
                applied_provider_patch = True
                logger.info(f"Applied dynamic structural patch to React state provider ({fn_name})")

        if not applied_provider_patch:
            # Fallback to static version profiles
            patched_gma = enhancer_common + '''function gMa({children:a,userStatus:b,lastSelectedAgentModel:c,setLastSelectedAgentModel:e,supportsCustomModels:f,lastModelDefaultOverrideVersionId:g,setLastModelDefaultOverrideVersionId:h,customModelsState:k}){b=__enhanceUserStatus(b);var [_selLabel,_setSelLabel]=(0,A.useState)(()=>{try{return localStorage.getItem("agy.selectedModelLabel")||null}catch(E){return null}}),[l,m]=(0,A.useState)(null),[n,q]=(0,A.useState)({}),[r,t]=(0,A.useState)(void 0),u=(0,A.useMemo)(()=>{var J=dMa(k);for(let L of J)L.disabled=!f;return J},[k,f]),v=(0,A.useMemo)(()=>[...(b?.cascadeModelConfigData?.clientModelConfigs||[]).map(Ck).filter(J=>J!==null).filter(J=>!J.disabled)],[b?.cascadeModelConfigData]),w=(0,A.useMemo)(()=>b?.cascadeModelConfigData?.defaultOverrideModelConfig,[b?.cascadeModelConfigData]);cMa(v,w,g,h,e);var x=(0,A.useMemo)(()=>{var J=b?.cascadeModelConfigData,L=J?.clientModelConfigs||[],N=J?.clientModelSorts||[];J=L.map(Ck).filter(O=>O!==null).filter(O=>!O.disabled);L=dma(L,N);return L.length>0?L:cma(J)},[b?.cascadeModelConfigData]),y=(0,A.useCallback)((J,L)=>{if(v.length!==0||u.length!==0){if(L){let N=v.find(O=>O.label===L||O.modelAlias===L)||u.find(O=>O.label===L);if(N)return N}if(J===I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&u.length>0)return u[0];if(J!==void 0&&J!==I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&(J=Dk(J,v)))return J;if(_selLabel){let N=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(N)return N}return v[0]??u.at(0)}},[v,u,_selLabel]),B=(0,A.useMemo)(()=>{if(v.length!==0||u.length!==0){if(_selLabel){let N=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(N)return N}return y(c,l)}},[y,c,v,u,l,_selLabel]),C=(0,A.useCallback)(J=>{if(J!==void 0&&(J=n[J],J!==void 0)){if(J.customLabel){let N=v.find(O=>O.label===J.customLabel||O.modelAlias===J.customLabel)||u.find(O=>O.label===J.customLabel);if(N)return N}return y(J.model,J.customLabel)}return B},[n,y,B,v,u]),D=(0,A.useCallback)((J,L,N,O,M)=>{J!==void 0&&q(Q=>{var P=Q[J],R={model:L,customLabel:O,contextWindow:Cz(P??r,L,M)};return P?.model===L&&P?.customLabel===O&&P?.contextWindow===R.contextWindow?Q:{...Q,[J]:R}});if(N||J===void 0)e(L),t(Q=>{var P=Cz(Q,L,M);return Q?.model===L&&Q?.contextWindow===P?Q:{model:L,contextWindow:P}}),m(O??null)},[e,r]),E=(0,A.useCallback)((J,L,N,O)=>{var M=eMa(v,u,J);if(M){_setSelLabel(J);try{localStorage.setItem("agy.selectedModelLabel",J)}catch(err){}var Q=u.some(P=>P.label===J);D(L,M.value,N,Q?J:O,O)}else console.error(`[Model Select] Invalid model label: ${J}`)},[v,u,D]),G=(0,A.useCallback)(J=>(J=J===void 0?void 0:n[J])?J.contextWindow:Cz(r,B?.value),[n,r,B]),F=(0,A.useCallback)((J,L,N)=>{var O=Cz(r,L);q(M=>J in M?M:{...M,[J]:{model:L,customLabel:N,contextWindow:O}})},[r]),H=(0,A.useCallback)(J=>{E(J,void 0,!0)},[E]),K=(0,A.useMemo)(()=>b?.cascadeModelConfigData===void 0,[b?.cascadeModelConfigData]);g=(0,A.useMemo)(()=>({modelSorts:x,visibleModelConfigs:v,customModels:u,currentModelConfig:B,setLastSelectedAgentModel:e,setCurrentModelConfigByLabel:H,supportsCustomModels:f,isModelListLoading:K,getModelConfigForConversation:C,setModelForConversation:D,setModelConfigByLabelForConversation:E,getContextWindowForConversation:G,ensureConversationModelSeeded:F}),[x,v,u,B,e,H,f,K,C,D,E,G,F]);return A.createElement(fMa.Provider,{value:g},a)}'''
            patched_ala = enhancer_common + '''function ALa({children:a,userStatus:b,lastSelectedAgentModel:c,setLastSelectedAgentModel:e,supportsCustomModels:f,lastModelDefaultOverrideVersionId:g,setLastModelDefaultOverrideVersionId:h,customModelsState:k}){b=__enhanceUserStatus(b);var [_selLabel,_setSelLabel]=(0,A.useState)(()=>{try{return localStorage.getItem("agy.selectedModelLabel")||null}catch(E){return null}}),[l,m]=(0,A.useState)(null),[n,q]=(0,A.useState)({}),[r,t]=(0,A.useState)(void 0),u=(0,A.useMemo)(()=>{var J=xLa(k);for(let L of J)L.disabled=!f;return J},[k,f]),v=(0,A.useMemo)(()=>[...(b?.cascadeModelConfigData?.clientModelConfigs||[]).map(tk).filter(J=>J!==null).filter(J=>!J.disabled)],[b?.cascadeModelConfigData]),w=(0,A.useMemo)(()=>b?.cascadeModelConfigData?.defaultOverrideModelConfig,[b?.cascadeModelConfigData]);wLa(v,w,g,h,e);var x=(0,A.useMemo)(()=>{var J=b?.cascadeModelConfigData,L=J?.clientModelConfigs||[],M=J?.clientModelSorts||[];J=L.map(tk).filter(O=>O!==null).filter(O=>!O.disabled);L=wla(L,M);return L.length>0?L:vla(J)},[b?.cascadeModelConfigData]),y=(0,A.useCallback)((J,L)=>{if(v.length!==0||u.length!==0){if(L){let M=v.find(O=>O.label===L||O.modelAlias===L)||u.find(O=>O.label===L);if(M)return M}if(J===I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&u.length>0)return u[0];if(J!==void 0&&J!==I.Model.GOOGLE_GEMINI_INTERNAL_BYOM&&(J=uk(J,v)))return J;if(_selLabel){let M=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(M)return M}return v[0]??u.at(0)}},[v,u,_selLabel]),B=(0,A.useMemo)(()=>{if(v.length!==0||u.length!==0){if(_selLabel){let M=v.find(O=>O.label===_selLabel||O.modelAlias===_selLabel)||u.find(O=>O.label===_selLabel);if(N)return N}return y(c,l)}},[y,c,v,u,l,_selLabel]),C=(0,A.useCallback)(J=>{if(J!==void 0&&(J=n[J],J!==void 0)){if(J.customLabel){let M=v.find(O=>O.label===J.customLabel||O.modelAlias===J.customLabel)||u.find(O=>O.label===J.customLabel);if(M)return M}return y(J.model,J.customLabel)}return B},[n,y,B,v,u]),D=(0,A.useCallback)((J,L,M,O,N)=>{J!==void 0&&q(P=>{var Q=P[J],R={model:L,customLabel:O,contextWindow:Gz(Q??r,L,N)};return Q?.model===L&&Q?.customLabel===O&&Q?.contextWindow===R.contextWindow?P:{...P,[J]:R}});if(M||J===void 0){e(L);t(P=>{var Q=Gz(P,L,N);return P?.model===L&&P?.contextWindow===Q?P:{model:L,contextWindow:Q}});m(O??null)}},[e,r]),E=(0,A.useCallback)((J,L,M,O)=>{var N=yLa(v,u,J);if(N){_setSelLabel(J);try{localStorage.setItem("agy.selectedModelLabel",J)}catch(err){}D(L,N.value,M,J,O)}else console.error(`[Model Select] Invalid model label: ${J}`)},[v,u,D]),F=(0,A.useCallback)(J=>(J=J===void 0?void 0:n[J])?J.contextWindow:Gz(r,B?.value),[n,r,B]),G=(0,A.useCallback)((J,L,M)=>{var O=Gz(r,L);q(N=>J in N?N:{...N,[J]:{model:L,customLabel:M,contextWindow:O}})},[r]),H=(0,A.useCallback)(J=>{E(J,void 0,!0)},[E]),K=(0,A.useMemo)(()=>b?.cascadeModelConfigData===void 0,[b?.cascadeModelConfigData]);g=(0,A.useMemo)(()=>({modelSorts:x,visibleModelConfigs:v,customModels:u,currentModelConfig:B,setLastSelectedAgentModel:e,setCurrentModelConfigByLabel:H,supportsCustomModels:f,isModelListLoading:K,getModelConfigForConversation:C,setModelForConversation:D,setModelConfigByLabelForConversation:E,getContextWindowForConversation:F,ensureConversationModelSeeded:G}),[x,v,u,B,e,H,f,K,C,D,E,F,G]);return A.createElement(zLa.Provider,{value:g},a)}'''

            if 'function gMa({' in js:
                target_start = 'function gMa({'
                target_end = '.Provider,{value:g},a)}'
                pos_start = js.find(target_start)
                if pos_start != -1:
                    pos_end = js.find(target_end, pos_start)
                    if pos_end != -1:
                        pos_end += len(target_end)
                        js = js[:pos_start] + patched_gma + js[pos_end:]
                        applied_provider_patch = True
            elif 'function ALa({' in js:
                target_start = 'function ALa({'
                target_end = '.Provider,{value:g},a)}'
                pos_start = js.find(target_start)
                if pos_start != -1:
                    pos_end = js.find(target_end, pos_start)
                    if pos_end != -1:
                        pos_end += len(target_end)
                        js = js[:pos_start] + patched_ala + js[pos_end:]
                        applied_provider_patch = True

            if not applied_provider_patch:
                logger.warning("Could not identify React state provider structure; proceeding with graceful degradation.")

    with open(main_js_path, "w", encoding="utf-8") as f:
        f.write(js)

    # 2. Patch index.html
    with open(index_html_path, "r", encoding="utf-8") as f:
        html = f.read()

    auto_script = '''    <script>
      // Antigravity Web Hub: Auto-unlock Developer & Google-internal capabilities
      try {
        if (window.__AGY_PROXY_ACTIVE__ === undefined) {
          window.__AGY_PROXY_ACTIVE__ = true;
        }
        try {
          localStorage.setItem("agy.proxyActive", window.__AGY_PROXY_ACTIVE__ ? "true" : "false");
        } catch (e) {}
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

    if "Auto-unlock Developer" not in html:
        if "  </head>" in html:
            html = html.replace("  </head>", auto_script)
        elif "</head>" in html:
            html = html.replace("</head>", auto_script.strip() + "\n  </head>")
        with open(index_html_path, "w", encoding="utf-8") as f:
            f.write(html)

    # 3. Write .patched completion marker
    with open(bundle_dir / ".patched", "w", encoding="utf-8") as f:
        f.write("patched=true\n")

    return True


def is_bundle_patched(bundle_dir: Path) -> bool:
    """Checks whether the extracted bundle is present and fully patched."""
    if not bundle_dir.is_dir():
        return False
    marker = bundle_dir / ".patched"
    main_js = bundle_dir / "main.js"
    index_html = bundle_dir / "index.html"
    if not (marker.is_file() and main_js.is_file() and index_html.is_file()):
        return False
    try:
        content = main_js.read_text(encoding="utf-8", errors="ignore")
        return (
            "restrictToCorpDomain:!1" in content
            and "MODEL_ENUM_MAP" in content
            and "_sep_ordered_v8" in content
            and "agy.selectedModelLabel" in content
        )
    except Exception:
        return False


def sync_bundle_proxy_mode(bundle_dir: Path, proxy_active: bool) -> None:
    """
    Updates the runtime proxy mode state in index.html so the UI knows
    whether to show Web models (when proxy is active) or only native Antigravity models (direct mode).
    """
    index_html_path = bundle_dir / "index.html"
    if not index_html_path.is_file():
        return
    try:
        html = index_html_path.read_text(encoding="utf-8")
        val_str = "true" if proxy_active else "false"
        script_pattern = re.compile(r'window\.__AGY_PROXY_ACTIVE__\s*=\s*(?:true|false);?')
        new_stmt = f'window.__AGY_PROXY_ACTIVE__ = {val_str}; try {{ localStorage.setItem("agy.proxyActive", "{val_str}"); }} catch (e) {{}}'
        if script_pattern.search(html):
            html = script_pattern.sub(new_stmt, html)
        elif "</head>" in html:
            html = html.replace("</head>", f"    <script>{new_stmt}</script>\n  </head>")
        index_html_path.write_text(html, encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not sync bundle proxy mode in index.html: {e}")


def prepare_patched_web_bundle(
    ls_bin: Path,
    bundle_dir: Optional[Path] = None,
    force: bool = False,
    direct: bool = False,
    proxy_active: bool = True,
) -> Path:
    """
    Ensures a patched Web UI bundle exists at bundle_dir, extracting and patching if necessary.
    Synchronizes runtime proxy mode (direct vs proxy) so only available models are shown.
    """
    target_dir = bundle_dir or DEFAULT_BUNDLE_DIR

    if force or not is_bundle_patched(target_dir):
        logger.info(f"Extracting and patching Web UI bundle to: {target_dir}")
        if not extract_web_bundle(ls_bin, target_dir):
            raise RuntimeError(f"Failed to extract web bundle from {ls_bin}")
        if not patch_web_bundle(target_dir):
            raise RuntimeError(f"Failed to apply patches to web bundle in {target_dir}")
        logger.info("Web UI bundle successfully prepared and patched.")
    else:
        logger.debug(f"Using existing patched web bundle at: {target_dir}")

    # Synchronize runtime proxy mode flag in index.html
    sync_bundle_proxy_mode(target_dir, proxy_active=proxy_active and not direct)

    return target_dir


def binary_supports_web_bundle(ls_bin: Path) -> bool:
    """Checks if the language_server binary supports the -web_bundle_path flag."""
    try:
        from agy_proxy.patcher import is_wrapper_script
        real_bin = ls_bin
        if is_wrapper_script(ls_bin):
            cand = ls_bin.parent / f"{ls_bin.name}.real"
            if cand.is_file():
                real_bin = cand
        if not real_bin.is_file():
            return True
        with open(real_bin, "rb") as f:
            data = f.read(120 * 1024 * 1024)
            return b"web_bundle_path" in data
    except Exception:
        return True


def build_web_args(
    ls_path: Path,
    port: int = DEFAULT_WEB_PORT,
    csrf_token: Optional[str] = None,
    proxy_url: Optional[str] = DEFAULT_PROXY_URL,
    ide_version: str = DEFAULT_IDE_VERSION,
    direct: bool = False,
    web_bundle_path: Optional[Path | str] = None,
) -> List[str]:
    """Constructs command line arguments for running language_server in standalone Web mode."""
    token = csrf_token or get_csrf_token()
    args = [
        str(ls_path),
        "--standalone",
        "--override_ide_name", "antigravity",
        "--subclient_type", "hub",
        "--override_ide_version", ide_version,
        "--override_user_agent_name", "antigravity",
        "--https_server_port", str(port),
        "--csrf_token", token,
        "--app_data_dir", "antigravity",
        "--enable_sidecars",
    ]

    # Connect to agy-proxy if active and direct mode is not forced, otherwise fallback to official Google backend
    if proxy_url and not direct:
        clean_url = proxy_url.rstrip("/")
        args.extend(["--api_server_url", clean_url, "--cloud_code_endpoint", clean_url])
    else:
        args.extend([
            "--api_server_url", DEFAULT_GOOGLE_API_URL,
            "--cloud_code_endpoint", DEFAULT_GOOGLE_CC_ENDPOINT,
        ])

    if web_bundle_path:
        if binary_supports_web_bundle(Path(ls_path)):
            args.extend(["--web_bundle_path", str(web_bundle_path)])
        else:
            logger.warning(f"Language server binary at {ls_path} does not support --web_bundle_path; skipping custom web bundle.")

    return args


def open_browser_async(url: str, browser_name: Optional[str] = None, delay: float = 2.5):
    """Opens the specified URL in a web browser in a background daemon thread."""
    def _open():
        time.sleep(delay)
        try:
            if browser_name:
                browser_bin = shutil.which(browser_name)
                if browser_bin:
                    subprocess.Popen([browser_bin, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
            # Check for xdg-open on Linux
            if sys.platform.startswith("linux") and shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            # Standard Python fallback
            webbrowser.open(url)
        except Exception as e:
            logger.debug(f"Could not open browser automatically: {e}")

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def get_web_status(port: int = DEFAULT_WEB_PORT) -> Dict[str, Any]:
    """Returns complete real-time status of Antigravity Web Mode."""
    instances = get_running_instances()
    port_busy = is_port_in_use(port)
    ls_standalone = False
    standalone_pid = None

    for ls in instances.get("language_server_details", []):
        if ls.get("standalone"):
            ls_standalone = True
            standalone_pid = ls.get("pid")
            break

    is_running = port_busy or ls_standalone
    ls_pids = instances.get("language_server_pids") or []
    primary_ls_pid = ls_pids[0] if ls_pids else None
    return {
        "status": "running" if is_running else "stopped",
        "port": port,
        "url": f"https://127.0.0.1:{port}/",
        "pid": standalone_pid or primary_ls_pid,
        "electron_running": instances.get("electron_running", False),
        "electron_pids": instances.get("electron_pids", []),
        "port_in_use": port_busy,
        "estimated_ram_saved_mb": 1600 if is_running and not instances.get("electron_running") else 0,
    }


def print_web_banner(
    url: str,
    port: int,
    csrf_token: str,
    proxy_url: Optional[str],
    proxy_active: bool,
    ls_path: Path,
    killed_electron: bool = False,
    log_path: Optional[Path] = None,
    direct: bool = False,
    web_bundle_path: Optional[Path | str] = None,
):
    """Renders a beautiful Rich banner for Antigravity Web Mode."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", no_wrap=True)
    table.add_column("Value")

    table.add_row("[bold cyan]🌐 Antigravity Web UI:[/bold cyan]", f"[bold green]{url}[/bold green]")
    table.add_row("[bold cyan]⚡ Performance Mode:[/bold cyan]", "[bold yellow]Standalone Web (No Electron)[/bold yellow]")
    table.add_row("[bold cyan]💾 Memory Optimization:[/bold cyan]", "[bold green]~1.6 GB RAM Saved[/bold green] [dim](Electron GUI skipped)[/dim]")

    if web_bundle_path:
        table.add_row("[bold cyan]🧩 Web UI Bundle:[/bold cyan]", f"[bold magenta]Patched Web Hub[/bold magenta] [dim]({web_bundle_path})[/dim]")

    if direct:
        proxy_display = "[bold green]Standalone Direct Mode[/bold green] [dim](Official Google Backend · Proxy Bypassed)[/dim]"
    elif proxy_active and proxy_url:
        proxy_display = f"[bold green]Proxy Mode (Connected)[/bold green] [dim]({proxy_url} · Multi-Account Pool Active)[/dim]"
    elif proxy_url:
        proxy_display = "[bold green]Standalone Direct Mode[/bold green] [dim](Official Google Backend · Proxy-Free)[/dim]"
    else:
        proxy_display = "[bold green]Standalone Direct Mode[/bold green] [dim](Official Google Backend)[/dim]"
    table.add_row("[bold cyan]🔄 Antigravity Mode:[/bold cyan]", proxy_display)

    table.add_row("[bold cyan]🔑 CSRF Token:[/bold cyan]", f"[dim]{csrf_token}[/dim]")
    table.add_row("[bold cyan]📦 Server Binary:[/bold cyan]", f"[dim]{ls_path}[/dim]")

    if log_path:
        table.add_row("[bold cyan]📄 Server Logs:[/bold cyan]", f"[dim]{log_path}[/dim]")

    if killed_electron:
        table.add_row("[bold cyan]🧹 Electron Cleanup:[/bold cyan]", "[bold green]Closed old Electron window to free memory[/bold green]")

    table.add_row(
        "[bold cyan]ℹ️  SSL Notice:[/bold cyan]",
        "[dim]Browser will ask to accept self-signed SSL certificate for local HTTPS. Click Advanced -> Proceed.[/dim]",
    )

    panel = Panel(
        table,
        title="[bold white]🚀 Google Antigravity Web Mode [dim](Zero Electron Overhead)[/dim][/bold white]",
        border_style="cyan",
        subtitle="[dim]Press Ctrl+C to stop server[/dim]",
        padding=(1, 2),
    )
    console.print(panel)


def launch_antigravity_web(
    port: int = DEFAULT_WEB_PORT,
    host: str = "127.0.0.1",
    proxy_url: Optional[str] = DEFAULT_PROXY_URL,
    proxy_port: int = DEFAULT_PROXY_PORT,
    open_browser: bool = False,
    no_open: Optional[bool] = None,
    browser: Optional[str] = None,
    kill_electron: bool = False,
    ls_path: Optional[str | Path] = None,
    editor_path: Optional[str | Path] = None,
    detach: bool = False,
    ide_version: str = DEFAULT_IDE_VERSION,
    verbose: bool = False,
    log_path: Optional[str | Path] = None,
    direct: bool = False,
    restart: bool = False,
    patched: bool = False,
    force_patch: bool = False,
    bundle_dir: Optional[str | Path] = None,
) -> int:
    """
    Main entry point for starting Antigravity in browser Web Mode.
    Handles discovery, Electron cleanup, proxy detection, browser opening, and process lifecycle.
    """
    resolved_ls = find_language_server(custom_path=ls_path or editor_path, interactive=True)
    if not resolved_ls or not resolved_ls.is_file():
        console.print("[bold red]❌ Error: Could not locate Antigravity language_server binary.[/bold red]")
        console.print("Please install Antigravity or specify the path via [bold cyan]--ls-path /path/to/binary[/bold cyan] or [bold cyan]-e /path/to/editor[/bold cyan].")
        console.print("You can also configure it permanently with: [bold cyan]agy-proxy config set ls-path <PATH>[/bold cyan]")
        return 1

    # Set ANTIGRAVITY_HARNESS_PATH so Python SDK and tools can find the running harness
    os.environ["ANTIGRAVITY_HARNESS_PATH"] = str(resolved_ls)

    # Prepare log path
    effective_log_path = Path(log_path) if log_path else Path.home() / ".config" / "Antigravity" / "logs" / "language_server.log"
    try:
        effective_log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Check running instances
    instances = get_running_instances()
    killed_any = False

    if instances.get("electron_running"):
        if kill_electron:
            console.print("[bold yellow]🧹 Terminating existing Electron Antigravity processes to free RAM...[/bold yellow]")
            killed = kill_electron_instances()
            killed_any = len(killed) > 0
            console.print(f"[bold green]✓ Stopped {len(killed)} Electron process(es).[/bold green]")
        else:
            console.print("[bold yellow]⚠️  Notice: Running Electron Antigravity instance detected.[/bold yellow]")
            console.print("Closing the Electron window will free ~1.6 GB of RAM. You can use [bold cyan]--kill-electron[/bold cyan] to do this automatically.")

    # Determine whether to auto-open browser (default: False to prevent tab spam)
    should_open = open_browser
    if no_open is not None and not open_browser:
        should_open = not no_open

    # Check proxy status first
    if direct:
        effective_proxy_url = None
        proxy_alive = False
    else:
        effective_proxy_url = proxy_url
        if effective_proxy_url and not effective_proxy_url.startswith("http"):
            effective_proxy_url = f"http://{effective_proxy_url}"
        proxy_alive = check_proxy_alive(effective_proxy_url) if effective_proxy_url else False

    # Check if a running standalone instance is in a mismatched mode (e.g. was pointing to dead proxy)
    running_standalone_details = [
        ls for ls in instances.get("language_server_details", []) if ls.get("standalone")
    ]
    should_restart_for_mode_switch = False
    if running_standalone_details and is_port_in_use(port, host):
        cmd_str = running_standalone_details[0].get("cmd", "")
        existing_points_to_proxy = "8000" in cmd_str or (effective_proxy_url and effective_proxy_url in cmd_str)
        desired_points_to_proxy = proxy_alive and not direct

        if existing_points_to_proxy and not desired_points_to_proxy:
            console.print("[bold yellow]🔄 Stale instance detected (pointing to offline proxy). Auto-restarting in Direct Google Mode...[/bold yellow]")
            should_restart_for_mode_switch = True
        elif not existing_points_to_proxy and desired_points_to_proxy:
            console.print("[bold yellow]🔄 Detected running instance in Direct mode while proxy is online. Auto-restarting in Proxy Mode...[/bold yellow]")
            should_restart_for_mode_switch = True

    if restart or should_restart_for_mode_switch:
        killed = kill_standalone_instances(port=port)
        if killed:
            console.print(f"[bold green]✓ Stopped {len(killed)} previous Antigravity Web process(es).[/bold green]")
        for _ in range(25):
            if not is_port_in_use(port, host):
                break
            time.sleep(0.1)
        instances = get_running_instances()

    # Check if port is already in use
    url = f"https://{host}:{port}/"
    if is_port_in_use(port, host):
        console.print(f"[bold yellow]⚠️  Port {port} is already in use.[/bold yellow]")
        if instances.get("language_server_running"):
            console.print(f"[bold green]✓ Antigravity Web is already running at:[/bold green] [bold cyan]{url}[/bold cyan]")
            if should_open:
                console.print("🌐 Opening web browser...")
                open_browser_async(url, browser_name=browser, delay=0.5)
            return 0
        else:
            console.print(f"[bold red]❌ Port {port} is occupied by another process. Please choose a different port with --port <number> or use --restart.[/bold red]")
            return 1

    token = get_csrf_token()
    target_bundle: Optional[Path] = None
    if patched:
        try:
            target_bundle = prepare_patched_web_bundle(
                resolved_ls,
                bundle_dir=Path(bundle_dir) if bundle_dir else None,
                force=force_patch,
                direct=direct,
                proxy_active=proxy_alive,
            )
        except Exception as e:
            console.print(f"[bold red]❌ Failed to prepare patched web bundle: {e}[/bold red]")
            return 1

    cmd = build_web_args(
        ls_path=resolved_ls,
        port=port,
        csrf_token=token,
        proxy_url=effective_proxy_url if proxy_alive else None,
        ide_version=ide_version,
        direct=direct,
        web_bundle_path=target_bundle,
    )

    print_web_banner(
        url=url,
        port=port,
        csrf_token=token,
        proxy_url=effective_proxy_url,
        proxy_active=proxy_alive,
        ls_path=resolved_ls,
        killed_electron=killed_any,
        log_path=effective_log_path if not verbose else None,
        direct=direct,
        web_bundle_path=target_bundle,
    )

    # Launch browser after delay only if requested
    if should_open:
        open_browser_async(url, browser_name=browser, delay=2.5)

    # Launch server process
    log_out = None
    try:
        if detach:
            console.print("[bold green]🚀 Running Antigravity Web in background daemon mode...[/bold green]")
            if not verbose:
                log_out = open(effective_log_path, "a", encoding="utf-8")
                target_out = log_out
                target_err = subprocess.STDOUT
            else:
                target_out = subprocess.DEVNULL
                target_err = subprocess.DEVNULL

            proc = subprocess.Popen(
                cmd,
                stdout=target_out,
                stderr=target_err,
                start_new_session=True,
            )
            console.print(f"Server started with PID: [bold cyan]{proc.pid}[/bold cyan]")
            return 0

        # Foreground mode: forward signals gracefully
        if not verbose:
            log_out = open(effective_log_path, "a", encoding="utf-8")
            proc = subprocess.Popen(cmd, stdout=log_out, stderr=subprocess.STDOUT)
        else:
            proc = subprocess.Popen(cmd)

        def _signal_handler(signum, frame):
            try:
                proc.terminate()
            except Exception:
                pass

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        # Health check: verify process didn't terminate immediately at startup
        try:
            exit_code = proc.wait(timeout=1.2)
            if exit_code != 0:
                console.print(f"[bold red]❌ Antigravity Web exited immediately with code {exit_code}.[/bold red]")
                if effective_log_path.is_file():
                    try:
                        log_lines = effective_log_path.read_text(encoding="utf-8").splitlines()[-15:]
                        if log_lines:
                            console.print("[bold yellow]Recent server log output:[/bold yellow]")
                            for line in log_lines:
                                console.print(f"[dim]{line}[/dim]")
                    except Exception:
                        pass
                return exit_code
        except subprocess.TimeoutExpired:
            # Process started successfully and is still running normally
            pass

        return proc.wait()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopping Antigravity Web Server...[/dim]")
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            pass
        return 0
    except Exception as e:
        console.print(f"[bold red]❌ Failed to start Antigravity Web Server:[/bold red] {e}")
        return 1
    finally:
        if log_out and not log_out.closed:
            try:
                log_out.flush()
                log_out.close()
            except Exception:
                pass
