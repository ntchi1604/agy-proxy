"""
Service management module for Antigravity Proxy.
Provides seamless installation, control, and status checking for background services
on Linux (systemd user unit) and macOS (launchd LaunchAgent).
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SYSTEMD_SERVICE_NAME = "agy-proxy.service"
LAUNCHD_PLIST_NAME = "com.antigravity.agy-proxy.plist"


def get_service_file_path() -> Path:
    """Returns the platform-specific path where the background service definition is stored."""
    system = platform.system()
    if system == "Linux":
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return config_dir / "systemd" / "user" / SYSTEMD_SERVICE_NAME
    elif system == "Darwin":
        return Path.home() / "Library" / "LaunchAgents" / LAUNCHD_PLIST_NAME
    else:
        return Path.home() / ".config" / "agy-proxy" / "agy-proxy.service"


def _resolve_exec_command(port: int = 8000, host: str = "127.0.0.1") -> list[str]:
    """Determines the appropriate command to run the proxy server."""
    agy_bin = shutil.which("agy-proxy")
    if agy_bin:
        return [agy_bin, "run", "--port", str(port), "--host", str(host)]
    return [sys.executable, "-m", "agy_proxy.cli", "run", "--port", str(port), "--host", str(host)]


def install_service(port: int = 8000, host: str = "127.0.0.1") -> tuple[bool, str]:
    """
    Installs and enables Antigravity Proxy as a user-level background service.
    Linux: systemd --user unit
    macOS: launchd LaunchAgent
    """
    system = platform.system()
    cmd_list = _resolve_exec_command(port=port, host=host)
    service_path = get_service_file_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)

    if system == "Linux":
        exec_str = " ".join(cmd_list)
        unit_content = f"""[Unit]
Description=Antigravity Multi-Account Proxy Service
After=network.target

[Service]
Type=simple
ExecStart={exec_str}
Restart=always
RestartSec=3s
Environment="PATH={os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')}"

[Install]
WantedBy=default.target
"""
        try:
            with open(service_path, "w", encoding="utf-8") as f:
                f.write(unit_content)
            os.chmod(service_path, 0o644)

            # Reload and enable
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", SYSTEMD_SERVICE_NAME], check=True, capture_output=True)
            return True, f"Successfully installed and started systemd user service at {service_path}"
        except Exception as e:
            return False, f"Failed to install systemd user service: {e}"

    elif system == "Darwin":
        log_dir = Path.home() / ".config" / "agy-proxy"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "service.log"

        args_xml = "\n".join(f"        <string>{arg}</string>" for arg in cmd_list)
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.antigravity.agy-proxy</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_file}</string>
    <key>StandardErrorPath</key>
    <string>{log_file}</string>
</dict>
</plist>
"""
        try:
            with open(service_path, "w", encoding="utf-8") as f:
                f.write(plist_content)
            os.chmod(service_path, 0o644)

            subprocess.run(["launchctl", "unload", str(service_path)], capture_output=True)
            subprocess.run(["launchctl", "load", "-w", str(service_path)], check=True, capture_output=True)
            return True, f"Successfully installed and loaded launchd LaunchAgent at {service_path}"
        except Exception as e:
            return False, f"Failed to install launchd service: {e}"

    else:
        return False, f"Automated service management is not supported on {system}."


def uninstall_service() -> tuple[bool, str]:
    """Stops, disables, and removes the Antigravity Proxy background service."""
    system = platform.system()
    service_path = get_service_file_path()

    if system == "Linux":
        try:
            subprocess.run(["systemctl", "--user", "stop", SYSTEMD_SERVICE_NAME], capture_output=True)
            subprocess.run(["systemctl", "--user", "disable", SYSTEMD_SERVICE_NAME], capture_output=True)
            if service_path.exists():
                service_path.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
            return True, f"Successfully uninstalled and removed {SYSTEMD_SERVICE_NAME}"
        except Exception as e:
            return False, f"Failed to uninstall systemd service: {e}"

    elif system == "Darwin":
        try:
            if service_path.exists():
                subprocess.run(["launchctl", "unload", "-w", str(service_path)], capture_output=True)
                service_path.unlink()
            return True, f"Successfully uninstalled and removed {LAUNCHD_PLIST_NAME}"
        except Exception as e:
            return False, f"Failed to uninstall launchd service: {e}"

    else:
        return False, f"Automated service management is not supported on {system}."


def get_service_status() -> dict[str, Any]:
    """Checks the status of the Antigravity Proxy background service."""
    system = platform.system()
    service_path = get_service_file_path()
    installed = service_path.exists()
    running = False
    details = ""

    if system == "Linux":
        if installed:
            res = subprocess.run(["systemctl", "--user", "is-active", SYSTEMD_SERVICE_NAME], capture_output=True, text=True)
            state = res.stdout.strip()
            running = (state == "active")
            stat_res = subprocess.run(["systemctl", "--user", "status", SYSTEMD_SERVICE_NAME, "--no-pager"], capture_output=True, text=True)
            details = stat_res.stdout.strip() or stat_res.stderr.strip()
        return {
            "platform": "Linux (systemd --user)",
            "service_file": str(service_path),
            "installed": installed,
            "running": running,
            "details": details,
        }

    elif system == "Darwin":
        if installed:
            res = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
            running = "com.antigravity.agy-proxy" in res.stdout
            details = "launchd service active" if running else "launchd service loaded but not running"
        return {
            "platform": "macOS (launchd)",
            "service_file": str(service_path),
            "installed": installed,
            "running": running,
            "details": details,
        }

    return {
        "platform": system,
        "service_file": str(service_path),
        "installed": installed,
        "running": False,
        "details": f"Platform {system} unsupported for native service manager",
    }


def start_service() -> tuple[bool, str]:
    """Starts the background service."""
    system = platform.system()
    service_path = get_service_file_path()
    if not service_path.exists():
        return False, "Service is not installed. Run 'agy-proxy service install' first."

    if system == "Linux":
        res = subprocess.run(["systemctl", "--user", "start", SYSTEMD_SERVICE_NAME], capture_output=True, text=True)
        return (res.returncode == 0), (res.stdout or res.stderr or "Service started")
    elif system == "Darwin":
        res = subprocess.run(["launchctl", "load", "-w", str(service_path)], capture_output=True, text=True)
        return (res.returncode == 0), (res.stdout or res.stderr or "Service loaded")
    return False, f"Unsupported platform {system}"


def stop_service() -> tuple[bool, str]:
    """Stops the background service."""
    system = platform.system()
    if system == "Linux":
        res = subprocess.run(["systemctl", "--user", "stop", SYSTEMD_SERVICE_NAME], capture_output=True, text=True)
        return (res.returncode == 0), (res.stdout or res.stderr or "Service stopped")
    elif system == "Darwin":
        service_path = get_service_file_path()
        res = subprocess.run(["launchctl", "unload", "-w", str(service_path)], capture_output=True, text=True)
        return (res.returncode == 0), (res.stdout or res.stderr or "Service unloaded")
    return False, f"Unsupported platform {system}"


def restart_service() -> tuple[bool, str]:
    """Restarts the background service."""
    system = platform.system()
    if system == "Linux":
        res = subprocess.run(["systemctl", "--user", "restart", SYSTEMD_SERVICE_NAME], capture_output=True, text=True)
        return (res.returncode == 0), (res.stdout or res.stderr or "Service restarted")
    elif system == "Darwin":
        stop_service()
        return start_service()
    return False, f"Unsupported platform {system}"
