import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from agy_proxy.cli import build_parser
from agy_proxy.server import create_app
from agy_proxy.web_launcher import (
    DEFAULT_IDE_VERSION,
    DEFAULT_WEB_PORT,
    build_web_args,
    check_proxy_alive,
    find_language_server,
    get_csrf_token,
    get_running_instances,
    get_web_status,
    is_port_in_use,
    kill_electron_instances,
)


def test_find_language_server_explicit_file(tmp_path):
    mock_bin = tmp_path / "language_server"
    mock_bin.write_text("#!/bin/sh\nexit 0\n")
    mock_bin.chmod(0o755)

    found = find_language_server(custom_path=mock_bin)
    assert found == mock_bin.resolve()


def test_find_language_server_explicit_dir(tmp_path):
    mock_bin = tmp_path / "language_server"
    mock_bin.write_text("#!/bin/sh\nexit 0\n")
    mock_bin.chmod(0o755)

    found = find_language_server(custom_path=tmp_path)
    assert found == mock_bin.resolve()


def test_find_language_server_env_var(tmp_path, monkeypatch):
    mock_bin = tmp_path / "language_server_linux_x64"
    mock_bin.write_text("#!/bin/sh\nexit 0\n")
    mock_bin.chmod(0o755)

    monkeypatch.setenv("ANTIGRAVITY_LS_PATH", str(mock_bin))
    found = find_language_server()
    assert found == mock_bin.resolve()


def test_get_csrf_token(monkeypatch):
    # When CSRF_TOKEN is in env
    monkeypatch.setenv("CSRF_TOKEN", "custom-secret-token-12345")
    assert get_csrf_token() == "custom-secret-token-12345"

    # When CSRF_TOKEN is unset
    monkeypatch.delenv("CSRF_TOKEN", raising=False)
    token = get_csrf_token()
    assert isinstance(token, str)
    assert len(token) >= 8


def test_is_port_in_use():
    # Bind a temporary socket to guarantee it's in use
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert is_port_in_use(port) is True

    # Once closed, verify it's free
    assert is_port_in_use(port) is False


def test_build_web_args_with_proxy(tmp_path):
    fake_bin = tmp_path / "language_server"
    args = build_web_args(
        ls_path=fake_bin,
        port=44741,
        csrf_token="my-token",
        proxy_url="http://127.0.0.1:8000",
        ide_version="2.23.0",
    )
    assert str(fake_bin) in args
    assert "--standalone" in args
    assert "--override_ide_name" in args
    assert "antigravity" in args
    assert "--subclient_type" in args
    assert "hub" in args
    assert "--override_ide_version" in args
    assert "2.23.0" in args
    assert "--https_server_port" in args
    assert "44741" in args
    assert "--csrf_token" in args
    assert "my-token" in args
    assert "--enable_sidecars" in args
    assert "--api_server_url" in args
    assert "http://127.0.0.1:8000" in args
    assert "--cloud_code_endpoint" in args


def test_build_web_args_without_proxy(tmp_path):
    fake_bin = tmp_path / "language_server"
    args = build_web_args(
        ls_path=fake_bin,
        port=44741,
        csrf_token="my-token",
        proxy_url=None,
    )
    assert "--standalone" in args
    assert "--api_server_url" not in args
    assert "--cloud_code_endpoint" not in args


def test_get_web_status_mock():
    with patch("agy_proxy.web_launcher.is_port_in_use", return_value=True), \
         patch("agy_proxy.web_launcher.get_running_instances", return_value={
             "electron_running": False,
             "electron_pids": [],
             "language_server_running": True,
             "language_server_pids": [99999],
             "language_server_details": [{"pid": 99999, "standalone": True}],
         }):
        status = get_web_status(port=44741)
        assert status["status"] == "running"
        assert status["url"] == "https://127.0.0.1:44741/"
        assert status["pid"] == 99999
        assert status["electron_running"] is False
        assert status["estimated_ram_saved_mb"] == 1600


def test_kill_electron_instances():
    mock_proc = MagicMock()
    mock_proc.is_running.return_value = False

    with patch("agy_proxy.web_launcher.get_running_instances", return_value={
        "electron_pids": [12345],
    }), patch("psutil.Process", return_value=mock_proc):
        killed = kill_electron_instances()
        assert killed == [12345]
        mock_proc.terminate.assert_called_once()


def test_cli_parser_web_subcommand():
    parser = build_parser()

    # Test 'web' subcommand
    args = parser.parse_args(["web", "--port", "44800", "--kill-electron", "--no-open"])
    assert args.subcommand == "web"
    assert args.port == 44800
    assert args.kill_electron is True
    assert args.no_open is True

    # Test alias 'antigravity-web'
    args_alias = parser.parse_args(["antigravity-web", "--status"])
    assert args_alias.subcommand == "antigravity-web"
    assert args_alias.status is True

    # Test alias 'web-mode'
    args_mode = parser.parse_args(["web-mode", "--browser", "helium", "-v"])
    assert args_mode.subcommand == "web-mode"
    assert args_mode.browser == "helium"
    assert args_mode.verbose is True

    # Test --debug sets verbose
    args_dbg = parser.parse_args(["web", "--debug"])
    assert args_dbg.subcommand == "web"
    assert args_dbg.verbose is True

    # Test default verbose is False
    args_default = parser.parse_args(["web"])
    assert args_default.verbose is False


def test_server_api_web_status():
    app = create_app()
    client = TestClient(app)

    with patch("agy_proxy.web_launcher.get_web_status", return_value={
        "status": "running",
        "port": 44741,
        "url": "https://127.0.0.1:44741/",
        "pid": 11872,
        "electron_running": False,
        "estimated_ram_saved_mb": 1600,
    }):
        resp = client.get("/api/web/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["url"] == "https://127.0.0.1:44741/"
        assert data["pid"] == 11872
        assert data["estimated_ram_saved_mb"] == 1600


def test_server_api_web_launch():
    app = create_app()
    client = TestClient(app)

    with patch("agy_proxy.web_launcher.launch_antigravity_web", return_value=0):
        resp = client.post("/api/web/launch", json={"port": 44741, "no_open": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["url"] == "https://127.0.0.1:44741/"
