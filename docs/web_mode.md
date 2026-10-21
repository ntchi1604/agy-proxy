# 🚀 Antigravity Web Mode & Patched Web Hub

Run Google Antigravity 2.0 directly in your browser with zero Electron overhead, saving **~1.6 GB+ of RAM** and unlocking hidden developer features.

---

## 📊 Overview & Resource Optimization

Google Antigravity 2.0 features an ultra-fast, native Go backend (`language_server`) hosting its full IDE and Agent web interface locally on port `44741`. The desktop application normally runs this inside an Electron wrapper (`/opt/Antigravity/antigravity`), which consumes **~1.6 GB to 2.0 GB+ of RAM** and spawns 10–15 background Chromium helper processes.

**Antigravity Web Mode** runs `language_server` directly in standalone mode, allowing you to use the full Antigravity 2.0 Web UI directly in your favorite browser (Helium, Chrome, Chromium, Firefox, Brave, Edge).

### 📈 Resource Benchmark

| Metric | Desktop App (Electron) | Web Mode (No-Electron) | Improvement |
| :--- | :--- | :--- | :--- |
| **RAM Footprint** | ~3.7 GB | **~2.1 GB** | **-1.6 GB RAM freed!** |
| **CPU Queue Load** | 8.0+ (Thermal throttling on 2-core CPUs) | **~2.0 (Smooth & Cool)** | **~75% CPU load drop** |
| **Process Count** | 10–15 Chromium processes | **1 lightweight Go binary** | Zero Electron bloat |
| **Feature Parity** | 100% | **100% (Identical)** | Subagents, chat, files, git, terminal |

---

## 🏃 Standard Web Mode (`agy-proxy web`)

```bash
# Start Antigravity in browser Web mode:
agy-proxy web

# Check current Web mode status:
agy-proxy web --status

# Automatically close running Electron window to free memory:
agy-proxy web -k

# Open browser automatically:
agy-proxy web -k -o

# Custom port or custom browser:
agy-proxy web --port 44741 --browser helium
```

### Combined One-Command Launch (Proxy + Web together)
```bash
# Starts agy-proxy and launches Antigravity Web simultaneously:
./start_proxy.sh --web
```

> [!NOTE]
> **Local SSL Certificate**: Because Antigravity serves local HTTPS with self-signed certificates, your browser will prompt to accept the certificate on first access. Simply click **Advanced** -> **Proceed to 127.0.0.1**.

---

## 🧪 Patched Web Hub (`agy-proxy web --patched`)

By default, the official Web UI limits certain advanced features to Google internal domains (`jetski.corp.google.com`) and displays non-functional Google3 Piper banners.

Using `agy-proxy web --patched` (or `agy-proxy web -P`) automatically extracts the embedded web assets (304 files) directly from `language_server`, applies clean client-side feature patches, and runs `language_server` with `--web_bundle_path` without modifying the original binary.

### 🌟 Unlocked Features

- 🔓 **Web Terminal Unlocked**: Completely bypasses the corporate domain lock (`restrictToCorpDomain: false`), allowing full bash terminal sessions directly within your browser.
- 📁 **File Explorer & Tabs**: Enables the native file tree and file browser side panel (`enable-file-explorer-tab`).
- ⚔️ **Battle Mode & Split View**: Enables multi-model side-by-side comparison and split chat layouts.
- 🤖 **Autonomous Mode**: Enables the autonomous execution toggle (`labs-autonomous-mode`) without repeated permission prompts.
- 💬 **Inline Actions & Thought Steering**: Displays floating toast action cards and allows editing agent thoughts in real-time.
- 🧹 **Google3 Clutter Removed**: Suppresses scary Google3 chat migration banners (`projectV5Migration`), broken `Agent Team` blaze calls, and inaccessible `Chief of Staff` concierge archives.

### 🚀 Usage

```bash
# 1-click run (auto-extracts bundle and patches UI):
agy-proxy web --patched

# Run with automatic Electron cleanup (-k) and browser launch (-o):
agy-proxy web --patched -k -o

# Restart server (kills previous instances on port):
agy-proxy web --patched -r

# Run on custom port:
agy-proxy web --patched -p 44742

# Point to custom language_server binary:
agy-proxy web --patched --ls-path /opt/Antigravity/resources/bin/language_server

# Force re-extracting and re-patching assets:
agy-proxy web --patched -f

# Show verbose language_server console output (debug mode):
agy-proxy web --patched -v
```

### 📋 Command Options for `agy-proxy web`

| Option | Description |
| :--- | :--- |
| `-P, --patched` | Launch with feature-patched Web UI bundle. |
| `-k, --kill-electron` | Automatically terminate running Electron instances. |
| `-o, --open` | Automatically open web browser on startup. |
| `-p, --port <port>` | Port for HTTPS web server (default: `44741`). |
| `-f, --force-patch` | Force re-extracting and re-patching Web UI bundle. |
| `-d, --bundle-dir <path>` | Target directory for extracted bundle (default: `~/.config/agy-proxy/web_ui`). |
| `--ls-path, --bin <path>` | Path to `language_server` (or `language_server.real`). |
| `-r, --restart` | Restart server (kills previous instance on port). |
| `-v, --debug` | Show verbose language_server console output. |
| `-f, --force` | Force re-extracting and re-patching bundle. |
| `-k, --kill-electron` | Automatically terminate running Electron instances to free memory. |
| `-r, --restart` | Restart web server (terminate any instance running on port). |
| `-o, --open` | Automatically open web browser after startup. |
| `--browser <cmd>` | Specify custom browser executable (e.g. `helium`, `google-chrome`). |
| `-v, --verbose, --debug` | Show raw `language_server` console output (default: logged to file). |
| `-h, --help` | Show help message. |

---

[← Back to Main README](../README.md)
