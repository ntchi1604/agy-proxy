"""
Antigravity Web Mode Launcher.
Launches the official Antigravity language_server in standalone HTTPS Web mode,
bypassing the heavy Electron GUI process and freeing ~1.6 GB+ of RAM.
Automatically connects to agy-proxy for multi-account pooling and quota failover.
"""

import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
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
        if cfg_ls and Path(cfg_ls).is_file():
            return Path(cfg_ls).resolve()
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


def build_web_args(
    ls_path: Path,
    port: int = DEFAULT_WEB_PORT,
    csrf_token: Optional[str] = None,
    proxy_url: Optional[str] = DEFAULT_PROXY_URL,
    ide_version: str = DEFAULT_IDE_VERSION,
    direct: bool = False,
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
    return {
        "status": "running" if is_running else "stopped",
        "port": port,
        "url": f"https://127.0.0.1:{port}/",
        "pid": standalone_pid or (instances.get("language_server_pids", [None])[0]),
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
):
    """Renders a beautiful Rich banner for Antigravity Web Mode."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", no_wrap=True)
    table.add_column("Value")

    table.add_row("[bold cyan]🌐 Antigravity Web UI:[/bold cyan]", f"[bold green]{url}[/bold green]")
    table.add_row("[bold cyan]⚡ Performance Mode:[/bold cyan]", "[bold yellow]Standalone Web (No Electron)[/bold yellow]")
    table.add_row("[bold cyan]💾 Memory Optimization:[/bold cyan]", "[bold green]~1.6 GB RAM Saved[/bold green] [dim](Electron GUI skipped)[/dim]")

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
    cmd = build_web_args(
        ls_path=resolved_ls,
        port=port,
        csrf_token=token,
        proxy_url=effective_proxy_url if proxy_alive else None,
        ide_version=ide_version,
        direct=direct,
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
