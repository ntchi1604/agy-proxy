import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from agy_proxy.cli import build_parser
from agy_proxy.server import create_app
from agy_proxy.web_launcher import (
    DEFAULT_GOOGLE_API_URL,
    DEFAULT_GOOGLE_CC_ENDPOINT,
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

    # persist=False prevents overwriting the real ~/.config/agy-proxy/config.json
    found = find_language_server(custom_path=mock_bin, persist=False)
    assert found == mock_bin.resolve()


def test_find_language_server_explicit_dir(tmp_path):
    mock_bin = tmp_path / "language_server"
    mock_bin.write_text("#!/bin/sh\nexit 0\n")
    mock_bin.chmod(0o755)

    # persist=False prevents overwriting the real ~/.config/agy-proxy/config.json
    found = find_language_server(custom_path=tmp_path, persist=False)
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
        ide_version="2.25.0",
    )
    assert str(fake_bin) in args
    assert "--standalone" in args
    assert "--override_ide_name" in args
    assert "antigravity" in args
    assert "--subclient_type" in args
    assert "hub" in args
    assert "--override_ide_version" in args
    assert "2.25.0" in args
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
    assert "--api_server_url" in args
    assert DEFAULT_GOOGLE_API_URL in args
    assert "--cloud_code_endpoint" in args
    assert DEFAULT_GOOGLE_CC_ENDPOINT in args


def test_build_web_args_direct_mode(tmp_path):
    fake_bin = tmp_path / "language_server"
    args = build_web_args(
        ls_path=fake_bin,
        port=44741,
        csrf_token="my-token",
        proxy_url="http://127.0.0.1:8000",
        direct=True,
    )
    assert "--standalone" in args
    assert "--api_server_url" in args
    assert DEFAULT_GOOGLE_API_URL in args
    assert "http://127.0.0.1:8000" not in args
    assert "--cloud_code_endpoint" in args
    assert DEFAULT_GOOGLE_CC_ENDPOINT in args


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

    # Test --open sets open
    args_open = parser.parse_args(["web", "--open"])
    assert args_open.open is True

    # Test default open is False and verbose is False
    args_default = parser.parse_args(["web"])
    assert args_default.verbose is False
    assert args_default.open is False
    assert args_default.direct is False

    # Test --direct and --no-proxy
    args_direct = parser.parse_args(["web", "--direct"])
    assert args_direct.direct is True

    args_no_proxy = parser.parse_args(["web", "--no-proxy"])
    assert args_no_proxy.direct is True


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


def test_build_web_args_with_bundle(tmp_path):
    fake_bin = tmp_path / "language_server"
    bundle_dir = tmp_path / "web_ui"
    args = build_web_args(
        ls_path=fake_bin,
        port=44741,
        csrf_token="my-token",
        web_bundle_path=bundle_dir,
    )
    assert "--web_bundle_path" in args
    assert str(bundle_dir) in args


def test_extract_and_patch_web_bundle(tmp_path):
    import io
    import zipfile
    from agy_proxy.web_launcher import (
        extract_web_bundle,
        patch_web_bundle,
        is_bundle_patched,
        prepare_patched_web_bundle,
    )

    # 1. Create a dummy zip archive containing main.js and index.html
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        dummy_js = (
            'restrictToCorpDomain:!0; '
            'var tk=a=>a.modelOrAlias?{label:a.label,value:a.modelOrAlias.choice.case==="model"?a.modelOrAlias.choice.value:I.Model.UNSPECIFIED,modelAlias:a.modelOrAlias.choice.case==="alias"?a.modelOrAlias.choice.value:void 0; '
            'function gMa({children:a,userStatus:b}){return .Provider,{value:g},a)}'
        )
        z.writestr("main.js", dummy_js)
        z.writestr("index.html", '<html><head><title>Test</title></head><body></body></html>')

    zip_bytes = zip_buffer.getvalue()

    # 2. Embed this zip inside a dummy binary
    fake_bin = tmp_path / "language_server"
    fake_bin.write_bytes(b"\x7fELF_PREFIX_HEADER" + zip_bytes)
    os.chmod(fake_bin, 0o755)

    out_bundle = tmp_path / "extracted_bundle"
    assert not is_bundle_patched(out_bundle)

    # 3. Test prepare_patched_web_bundle
    res_dir = prepare_patched_web_bundle(fake_bin, bundle_dir=out_bundle, force=True)
    assert res_dir == out_bundle
    assert is_bundle_patched(out_bundle)

    # Check patched main.js content
    main_js_content = (out_bundle / "main.js").read_text()
    assert "MODEL_ENUM_MAP" in main_js_content
    assert "_sep_ordered_v8" in main_js_content
    assert "agy.selectedModelLabel" in main_js_content

    # Check patched index.html content
    index_html_content = (out_bundle / "index.html").read_text()
    assert "Auto-unlock Developer" in index_html_content
    assert "enable-jetbox-terminal-v2" in index_html_content


def test_cli_web_patched_flags():
    parser = build_parser()
    args_p = parser.parse_args(["web", "--patched", "-f", "-d", "/tmp/custom_bundle"])
    assert args_p.subcommand == "web"
    assert args_p.patched is True
    assert args_p.force_patch is True
    assert args_p.bundle_dir == "/tmp/custom_bundle"

    args_p_short = parser.parse_args(["web", "-P"])
    assert args_p_short.patched is True
