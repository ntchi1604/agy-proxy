# ⚡ Antigravity Proxy (agy-proxy)

A high-performance Python proxy server that exposes Google Antigravity & Gemini Code Assist as **standard OpenAI (`/v1/chat/completions`)**, **OpenAI Responses API (`/v1/responses`)**, **Anthropic Claude (`/v1/messages`)**, and **Gemini Native (`/v1beta/...`)** API endpoints.

Equipped with **Multi-Account Pooling**, **Automatic 429 & 5xx Quota Failover**, **Upstream Proxy Routing**, **Antigravity IDE Language Server Patcher**, **Roo Code / Cline Schema Flattening & Tool Pairing Protection**, and a **built-in Web Dashboard & Live Playground**.

---

## ⚠️ Disclaimer & Terms of Service Notice

> [!IMPORTANT]
> **This project is developed independently for educational, research, API interoperability, and personal non-commercial evaluation purposes only.**
>
> - **No Affiliation**: This software is not affiliated with, endorsed by, maintained by, or sponsored by Google LLC, Anthropic PBC, or any of their subsidiaries.
> - **User Responsibility**: By using this software, you acknowledge and agree that you are solely responsible for your own account usage and for complying with the respective platform Terms of Service, Acceptable Use Policies, rate limits, and API licensing agreements of Google Cloud, Google AI Studio, Anthropic, and any other third-party services.
> - **No Warranty**: This software is provided "AS IS" without warranties or conditions of any kind, either express or implied. The authors and maintainers assume no liability for any direct, indirect, incidental, or consequential damages resulting from the use or misuse of this software, including but not limited to quota exhaustion, service disruption, or account suspension.

---

## 🔗 Official Antigravity Tools
This proxy is designed to supercharge the official Google Antigravity ecosystem. You can download the official clients here:
- **[Antigravity Hub (Antigravity 2.0 Web Agent)](https://antigravity.google/product/antigravity-2)**
- **[Antigravity CLI](https://antigravity.google/product/antigravity-cli)**
- **[Official Homepage](https://antigravity.google/)**

---

## 🌟 Key Features

- 🔄 **OpenAI, Responses API, Anthropic & Gemini Compatible Endpoints**:
  - Full support for OpenAI Chat Completions (`/v1/chat/completions`) and the latest **OpenAI Responses API (`/v1/responses`)** with native **WebSocket (`ws://`) and HTTP SSE streaming** for **OpenAI Codex CLI (v0.150+)**.
  - Full support for streaming (`stream: true` SSE) and non-streaming responses.
  - Thinking / Reasoning process extracted to `delta.reasoning_content` (OpenAI) and `thinking` blocks (Anthropic) for reasoning models (`gemini-3.8-flash-high`, `gemini-3.7-flash-high`, `claude-opus-4-6-thinking`).
  - Native Multi-turn Tool & Function Calling support (`tools`, `tool_choice`, `tool_use`, `tool_result`).
  - Multimodal input support (Images via base64 data URIs and URLs).
  - 🌐 **Built-in Live Web Search**: Native **Google Grounding Search (Vertex AI)** with automatic multi-engine fallbacks (**DuckDuckGo**, **Bing**, **Brave**) for coding agents and tools (`WebSearch`, `web_search`) without requiring external API keys.
- 👥 **Multi-Account Pooling & Automatic 429 / 5xx Failover**:
  - Pool multiple Google Antigravity accounts simultaneously to multiply rate limits and concurrent request capacity.
  - **Multi-Candidate Failover Loop**: When an account encounters a `429 Too Many Requests` rate limit, proxy marks it rate-limited for 60s and immediately retries on the next healthy account in the pool without dropping the client stream.
  - **Server Error Recovery (5xx)**: Automatically fails over to alternate pool accounts upon receiving upstream `500`, `502`, `503`, or `504` errors during content generation.
  - **Automatic 401 Re-Authentication**: Seamlessly triggers background token refresh (`refresh_access_token(force=True)`) and immediate retry on expired sessions.
  - **Zero-Delay Recovery**: Injects standard `Retry-After: 2` headers to prevent coding agents (Claude Code, Cursor, Aider, Roo Code) from locking up in multi-minute exponential backoff retry delays.
  - **Proxy Tunneling & Persistence**: Supports per-account `proxy_url` (saved across sessions and editable in Web UI/API) as well as global environment variables (`AGY_UPSTREAM_PROXY`, `ALL_PROXY`, `HTTP_PROXY`, `HTTPS_PROXY`) for corporate firewalls and Geo-Bypass.
- 🖥️ **Antigravity IDE Integration & Language Server Patcher**:
  - Native helper script [`patch_language_server.sh`](patch_language_server.sh) to transparently route Antigravity IDE's internal `language_server` through `agy-proxy`.
  - Non-destructive wrapper injection with automatic backup (`language_server.real`), automated path detection, health-check startup wait, process status inspection, and 1-command restore.
- 🎭 **Claude Role Sanitization & Error 500 Prevention**:
  - Automatically normalizes all message roles (`user`, `context` -> `user`; `model`, `assistant` -> `model` strictly in lowercase) and extracts system instructions into `systemInstruction`.
  - Completely eliminates upstream Google CloudCode `HTTP 500 Internal Server Error` when using Claude models (`claude-sonnet-4-6`, `claude-opus-4-6-thinking`).
- 🧩 **Roo Code & Cline Optimization**:
  - **Custom Tool Schema Support**: Deeply unpacks tool definitions from `tool.custom.input_schema`, `tool.custom.parameters`, `tool.custom.name`, and `tool.custom.description`.
  - **Schema Flattening (`sanitize_gemini_schema`)**: Flattens `anyOf`, `oneOf`, `allOf`, maps union nullables (`["string", "null"]` -> `type: "string", nullable: true`), and strips unsupported metadata (`$schema`, `definitions`, `additionalProperties`) preventing Gemini Error 400 validation failures.
  - **Tool Pairing Integrity (`ensure_tool_pairing_integrity`)**: Enforces strict 1:1 pairing between model `functionCall` turns and user `functionResponse` turns, caching thought signatures and resolving orphaned responses so conversation histories never crash downstream translations.
- 🗜 **Context Compactor & Auto-Summarization (Token Saver)**:
  - Automatically compresses long conversation histories using `gemini-3.1-flash-lite` before reaching token limits, saving **80% to 95%+ tokens** and preventing Google's 1,048,576 token hard limit (Error 400).
  - Native interception of agent `/compact` and `/autocompact` commands with structured 9-section summarization schema.
  - Interactive threshold slider (30k – 200k tokens) and toggle controls in the Web Dashboard.
- ⚡ **Intelligent Background Task Optimization**:
  - Automatically detects non-interactive tasks (title generation, context compaction, checkpoints) and routes them to lightweight, fast models (`gemini-3.1-flash-lite`) with 0 thinking budget to save 100% of your primary model quotas.
- 🔑 **Interactive OAuth PKCE Login (Web UI & CLI)**:
  - Add secondary Google accounts in 2 clicks via the Web UI ("➕ Add Google Account") or via terminal: `uv run python main.py auth login`.
  - Support for Google AI Studio API Keys with automatic dynamic model discovery.
- 📊 **Modern Web UI Dashboard & Playground**:
  - View all pooled Google accounts, avatars, active tiers, and live Gemini & Claude quota progress bars.
  - Interactive live chat playground with markdown rendering and collapsible thinking blocks.
  - Collapsible account groups (OAuth, Web, API Keys) with per-section Enable/Disable controls and toolbar batch actions.
  - Per-account proxy URL configuration, pause/resume toggles, and one-click account deletion.
- 🔄 **Antigravity CLI & Standalone Session Switcher**:
  - Live detection showing which accounts are currently active in **Antigravity CLI** (`~/.gemini/antigravity-cli/`) and **Antigravity 2.0 Web Agent** (`~/.gemini/jetski-standalone-oauth-token`).
  - Interactive Web UI modal to switch sessions selectively: **CLI Only**, **Standalone Only**, or **All (CLI + Standalone)**.
  - Strict compliance with official `antigravity-oauth-token` JSON schema (atomic writes, zero extra metadata, automated `.bak` backups, strict `0600` permissions).
- 🌐 **Cloudflare Edge Worker v2.2.0**:
  - Standalone serverless edge proxy supporting 100% cloud deployment with multi-account failover, Claude Code CLI bootstrap, role sanitization, and full model mappings.

---

## 🚀 Quick Start

### 1. One-Line Fast Install (Linux, macOS, Windows) ⚡

Install the pre-built standalone binary directly with a single command without needing Python:

#### 🔹 Linux & macOS
```bash
curl -fsSL https://raw.githubusercontent.com/kqlio67/agy-proxy/main/install.sh | bash
```

#### 🔹 Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/kqlio67/agy-proxy/main/install.ps1 | iex
```

#### 🔹 Windows (Command Prompt)
```cmd
curl -fsSL https://raw.githubusercontent.com/kqlio67/agy-proxy/main/install.cmd -o install.cmd && install.cmd && del install.cmd
```

Then simply start the proxy anywhere:
```bash
agy-proxy --port 8000
```

---

### 2. Run with Docker / Docker Compose 🐳

```bash
# Quick Docker Run:
docker run -d -p 8000:8000 \
  -v ~/.config/agy-proxy:/home/appuser/.config/agy-proxy \
  --name agy-proxy ghcr.io/kqlio67/agy-proxy:latest

# Or using Docker Compose:
docker compose up -d
```

---

### 3. Run via 1-Click Scripts (Repository Source)

- **Linux & macOS**:
  ```bash
  ./start_proxy.sh --port 8000
  ```
- **Windows (CMD / PowerShell / Explorer)**:
  ```cmd
  start_proxy.bat --port 8000
  ```

---

### 4. Run via Python / UV / Pip (Source)

```bash
# Clone the repository
git clone https://github.com/kqlio67/agy-proxy.git
cd agy-proxy

# Run instantly with UV (Recommended):
uv run python main.py --port 8000

# OR install with standard pip:
pip install -e .
agy-proxy --port 8000

# OR run directly with Python:
python main.py --port 8000
```

---

### 5. In-Place Self Update 🔄

Check and update Antigravity Proxy directly from the CLI:

```bash
# Check if a new version is available:
agy-proxy update --check

# Download & apply the latest update:
agy-proxy update
```

---

### 6. Run on Android via Termux 📱

Run Antigravity Proxy directly on your Android phone without root:

```bash
# 1. Update Termux and install Python + Git
pkg update -y && pkg install python git -y

# 2. Clone and install dependencies
git clone https://github.com/kqlio67/agy-proxy.git
cd agy-proxy
pip install -r requirements.txt

# 3. Start the proxy
python main.py --port 8000

# (Optional: expose to your local Wi-Fi network so your PC/laptop can connect to phone)
python main.py --host 0.0.0.0 --port 8000
```
Open **`http://localhost:8000`** in Chrome / Firefox on your phone to view the dashboard!

---

### 7. Run via Pre-built Standalone Binaries (Zero Dependencies)

Download the single executable for your OS & architecture from **[GitHub Releases](https://github.com/kqlio67/agy-proxy/releases)**:

- **Linux (x86_64 / amd64)**: `./agy-proxy --port 8000`
- **Linux ARM64 (Raspberry Pi 3/4/5, Orange Pi, ARM VPS)**: `./agy-proxy --port 8000`
- **Windows (x64)**: `agy-proxy.exe --port 8000`
- **macOS (Apple Silicon M1/M2/M3/M4)**: `./agy-proxy --port 8000`

*(To compile a single executable locally on your machine: `python build_binary.py`)*

---

Open **`http://localhost:8000`** in your browser to access the Web Dashboard & Account Pool Manager!

---

## 🛠 Integration Guides

> [!TIP]
> **Universal Compatibility**: Antigravity Proxy works seamlessly with **any** AI coding agent, editor, extension, or CLI tool that connects to OpenAI (`/v1/chat/completions`), OpenAI Responses (`/v1/responses`), or Anthropic (`/v1/messages`) APIs—including **Antigravity IDE**, **Cursor**, **Windsurf**, **VS Code** (Continue, Roo Code / Cline), **Claude Code CLI**, **OpenAI Codex CLI**, **Aider**, and custom scripts.

---

### 1. 🖥️ Google Antigravity 2.0 & Antigravity IDE (Standalone) Integration

Antigravity Proxy includes a dedicated helper script, [`patch_language_server.sh`](patch_language_server.sh), that patches the official **Google Antigravity 2.0** and **Antigravity IDE (Standalone)** internal `language_server` binary. This routes completions, chats, and model queries through `agy-proxy`, granting both applications access to pooled accounts, multi-candidate failover, custom upstream proxies, and Claude model routing.

#### 🔹 Supported Applications
- **Google Antigravity 2.0** (v2.19.1+ Desktop Application):
  - Binary location: `/opt/Antigravity/resources/bin/language_server`
- **Google Antigravity IDE (Standalone)** (v2.5.5+ Dedicated Editor):
  - Binary location: `resources/app/extensions/antigravity/bin/language_server_linux_x64` (or macOS `language_server_darwin_*`)
- **Antigravity for IDEs (Extensions)** (VS Code, JetBrains, Visual Studio, Zed, Xcode):
  - Seamlessly supported via CloudCode internal passthrough (`/v1internal:*`) and automated OAuth token sync from `state.vscdb`.

#### 🔹 How It Works
1. Automatically detects candidate installation directories for both **Antigravity 2.0** and **Antigravity IDE (Standalone)** on Linux and macOS:
   - `/opt/Antigravity` (and `/opt/Antigravity/resources/bin`)
   - `/opt/Antigravity IDE` (and `resources/app/extensions/antigravity/bin`)
   - `~/.local/share/Antigravity`
   - `~/.local/share/Antigravity IDE`
   - `/Applications/Antigravity.app`
   - `/Applications/Antigravity IDE.app`
   - Custom editor or binary paths via `-e, --editor <PATH>`, `-f, --file <PATH>`, `--dir <PATH>`, or positional argument
2. **Smart Editor Discovery**: when you specify an editor root folder (e.g. `/opt/Antigravity`, `/opt/Antigravity IDE`, or `~/Downloads/Antigravity IDE`), the script automatically searches through known subpaths and directory hierarchy to find the exact `language_server` binary.
3. Safely backs up the original binary to `*.real` (`language_server.real` or `language_server_linux_x64.real`).
4. Installs a non-destructive wrapper script with **Auto-Fallback (Direct Bypass)**:
   - When `agy-proxy` is running: intercepts and routes completions/chats through the proxy.
   - When `agy-proxy` is stopped/offline: automatically runs the original binary in native direct mode (connecting directly to Google backend) without breaking or stalling the editor.
5. **Dynamic Reconnect**: when you start the proxy (`./start_proxy.sh`), it detects if an Antigravity language server is currently running in direct mode and gracefully signals it to reload and latch onto the proxy in ~1s without losing open tabs or restarting the editor window.
6. When you execute `restart`, it terminates the active process so the editor automatically respawns it using the wrapper.

#### 🔹 Quick Usage
```bash
# Check current patching and process status (auto-detects Antigravity 2.0 or Antigravity IDE):
./patch_language_server.sh status

# Check status by pointing to an editor installation directory (auto-searches for binary):
./patch_language_server.sh status -e /opt/Antigravity
./patch_language_server.sh status -e "/opt/Antigravity IDE"
./patch_language_server.sh status "~/Downloads/Antigravity IDE"

# Patch automatically (using default port 8000):
./patch_language_server.sh patch

# Patch by editor directory or specific binary:
./patch_language_server.sh patch -e "/opt/Antigravity IDE"
./patch_language_server.sh patch "/opt/Antigravity"
./patch_language_server.sh patch -f "/path/to/.../bin/language_server_linux_x64"

# Patch with custom port or URL:
./patch_language_server.sh patch --port 8080
./patch_language_server.sh patch --url "http://127.0.0.1:8000"

# Restart language_server so editor respawns it with proxy wrapper:
./patch_language_server.sh restart

# Restore original unmodified binary (clean unpatch):
./patch_language_server.sh restore
./patch_language_server.sh restore -e "/opt/Antigravity IDE"
```

#### 🔹 Command & Flag Reference
| Command / Flag | Description |
|---|---|
| `patch` | Backs up original binary to `.real` and installs proxy wrapper script. |
| `restore` / `unpatch` | Restores original binary from `.real` and removes wrapper script. |
| `status` | Checks wrapper installation, binary integrity, PID, and tests proxy connectivity. |
| `restart` | Sends `SIGTERM` to running `language_server` so Antigravity IDE respawns it. |
| `kill` | Forcefully terminates running `language_server` processes. |
| `-e, --editor <PATH>` | Editor installation root (e.g. `/opt/Antigravity`, auto-locates binary). |
| `-f, --file, --path <PATH>` | Explicit path to `language_server` binary or editor directory. |
| `--dir <PATH>` | Directory containing the `language_server` executable or editor root. |
| `--port <PORT>` | Port where `agy-proxy` is listening (default: `8000` or `$PORT`). |
| `--host <HOST>` | Host where `agy-proxy` is listening (default: `127.0.0.1` or `$HOST`). |
| `--url <URL>` | Full proxy base URL (e.g. `http://127.0.0.1:8080` or Cloudflare Worker URL). |
| `--timeout <SECONDS>` | Max seconds to wait for proxy health-check at startup (default: `2`, `0` to disable). |
| `--no-wait` | Disable startup wait check before executing the binary. |
| `-y, --yes` | Automatically answer yes to all confirmation prompts. |

---

### 2. 🤖 Claude Code CLI

#### 🔹 1-Click Launch Scripts
```bash
# Linux / macOS / Termux:
./run_claude.sh

# Launch on a custom proxy port:
./run_claude.sh -p 8080

# Launch with a specific model (e.g., Claude Sonnet 4.6):
./run_claude.sh -p 8080 -m claude-sonnet-4-6

# Pass direct arguments to Claude Code:
./run_claude.sh -p 8080 -- --dangerously-skip-permissions "Explain this repo"
```

```cmd
:: Windows (Command Prompt / PowerShell):
run_claude.bat
run_claude.bat -p 8080 -m gemini-3.8-flash-high
```

#### 🔹 Persistent Configuration via CLI (`setup-claude`)
You can configure your local `~/.claude/settings.json` automatically:
```bash
# Configure Claude Code settings to route through agy-proxy:
agy-proxy setup-claude --port 8000 --model claude-sonnet-4-6

# Restore previous Claude Code configuration:
agy-proxy restore-claude
```

#### 🔹 Manual Launch (Direct Environment Variables)
```bash
# Linux / macOS / Termux:
ANTHROPIC_BASE_URL="http://127.0.0.1:8000" ANTHROPIC_API_KEY="dummy" ANTHROPIC_MODEL="gemini-3.8-flash-high" claude

# Windows PowerShell:
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8000"; $env:ANTHROPIC_API_KEY="dummy"; $env:ANTHROPIC_MODEL="gemini-3.8-flash-high"; claude

# Windows CMD:
set ANTHROPIC_BASE_URL=http://127.0.0.1:8000 && set ANTHROPIC_API_KEY=dummy && set ANTHROPIC_MODEL=gemini-3.8-flash-high && claude
```

---

### 3. ⌨️ OpenAI Codex CLI (v0.150+)

OpenAI Codex CLI uses the latest OpenAI Responses API (`/v1/responses`). Antigravity Proxy natively supports both **WebSocket (`ws://`)** and **HTTP SSE streaming** for Codex CLI with zero latency.

#### 🔹 Option A — 1-Click Launcher (`run_codex.sh`):
```bash
# Interactive mode with Antigravity model catalog:
./run_codex.sh

# Launch with a specific model:
./run_codex.sh -m claude-sonnet-4-6
./run_codex.sh -m gemini-3.8-flash-high
./run_codex.sh -m gpt-6-astra
```

#### 🔹 Option B — Ephemeral Run (`agy-proxy codex`):
```bash
# Launches codex through the proxy without modifying ~/.codex/config.toml:
agy-proxy codex -m gemini-3.8-flash-high
```

#### 🔹 Option C — Persistent Configuration (`~/.codex/config.toml`):
```bash
# Automatically configure ~/.codex/config.toml and model catalog:
agy-proxy setup-codex --port 8000 --model gemini-3.8-flash-high

# Or restore original config:
agy-proxy restore-codex
```

Or manually configure `~/.codex/config.toml`:
```toml
openai_base_url = "http://127.0.0.1:8000/v1"
model = "gemini-3.8-flash-high"
model_catalog_json = "~/.codex/antigravity_models.json"
```

> [!NOTE]
> Codex CLI built-in model names (`gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.2`) are automatically routed to corresponding Gemini models with full reasoning and thinking budgets.

---

### 4. 💻 IDEs & Code Editors (Cursor, Windsurf, VS Code)

#### 🔹 Cursor
1. Open **Settings** (`Ctrl+,` or `Cmd+,`) -> **Models**.
2. Enable **OpenAI API Key**:
   - **OpenAI Base URL**: `http://127.0.0.1:8000/v1`
   - **OpenAI API Key**: `dummy` (or your `PROXY_API_KEY`)
3. In **Model Names**, add:
   - `gemini-3.8-flash-high` *(Default flagship)*
   - `gemini-3.8-flash-medium`
   - `gemini-3.7-flash-high`
   - `claude-sonnet-4-6`
   - `claude-opus-4-6-thinking`
   - `gpt-4o`

#### 🔹 Windsurf / Codeium
1. Open **Settings** -> **Custom OpenAI Model Provider**.
2. Configure:
   - **Base URL**: `http://127.0.0.1:8000/v1`
   - **API Key**: `dummy`
   - **Model**: `gemini-3.8-flash-high` or `claude-sonnet-4-6`

#### 🔹 VS Code — Continue Extension
Add the following to your `~/.continue/config.json`:
```json
{
  "models": [
    {
      "title": "Antigravity Gemini 3.8 Flash",
      "provider": "openai",
      "model": "gemini-3.8-flash-high",
      "apiBase": "http://127.0.0.1:8000/v1",
      "apiKey": "dummy"
    },
    {
      "title": "Antigravity Claude Sonnet 4.6",
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "apiBase": "http://127.0.0.1:8000/v1",
      "apiKey": "dummy"
    }
  ]
}
```

#### 🔹 VS Code — Roo Code / Cline (Claude Dev)
Roo Code and Cline work with Antigravity Proxy via **either** the Anthropic or OpenAI Compatible providers.

##### Provider Configuration:
- **Anthropic Provider**:
  - **Base URL**: `http://127.0.0.1:8000`
  - **API Key**: `dummy`
  - **Model ID**: `gemini-3.8-flash-high` or `claude-sonnet-4-6`
- **OpenAI Compatible Provider**:
  - **Base URL**: `http://127.0.0.1:8000/v1`
  - **API Key**: `dummy`
  - **Model ID**: `gemini-3.8-flash-high` or `claude-sonnet-4-6`

##### 🛡️ Built-in Roo Code / Cline Optimizations in Antigravity Proxy:
1. **Custom Input Schema Extraction**: Resolves tool parameters when Roo Code packages them inside `tool.custom.input_schema` or `tool.custom.parameters`.
2. **Schema Sanitization (`sanitize_gemini_schema`)**: Flattens `anyOf`, `oneOf`, `allOf` constructs, resolves union nullables (`["string", "null"]` -> `nullable: true`), and strips unsupported metadata (`$schema`, `definitions`, `additionalProperties`) preventing Gemini 400 rejection.
3. **Tool Pairing Integrity (`ensure_tool_pairing_integrity`)**: Enforces 1:1 pairing between model tool calls and user tool results, preventing orphaned turns or mismatched call IDs from breaking upstream context translations.

---

### 5. 🧑‍💻 CLI Coding Agents (Aider, OpenCode)

#### 🔹 Aider
```bash
# Using OpenAI endpoint:
OPENAI_API_BASE="http://127.0.0.1:8000/v1" \
OPENAI_API_KEY="dummy" \
aider --model openai/gemini-3.8-flash-high

# Using Anthropic endpoint:
ANTHROPIC_BASE_URL="http://127.0.0.1:8000" \
ANTHROPIC_API_KEY="dummy" \
aider --model anthropic/claude-sonnet-4-6
```

---

### 6. 🌐 Cloudflare Edge Worker & Remote Access

The repository includes a production-ready **Cloudflare Worker** ([`cloudflare/`](cloudflare/)) supporting two modes:

#### 🔹 Mode 1: Geo-Bypass Upstream Gateway (Recommended for local dev)
Routes all Google CloudCode API requests from your local `agy-proxy` through Cloudflare's global edge network to bypass regional IP restrictions with 0% VPN overhead:
```bash
# Deploy worker in 1 command:
cd cloudflare && npx wrangler deploy

# Start local proxy routing through Cloudflare:
agy-proxy --port 8000 --cloudflare-url "https://agy-proxy-edge.<your-subdomain>.workers.dev"

# OR via environment variable:
export CLOUDFLARE_UPSTREAM_URL="https://agy-proxy-edge.<your-subdomain>.workers.dev"
agy-proxy --port 8000
```

#### 🔹 Mode 2: 100% Serverless Edge Mode (No PC needed, 24/7 in Cloud)
Deploy your account pool directly into Cloudflare's serverless edge:
```bash
cd cloudflare
# Upload your local accounts pool to Cloudflare Secrets:
npx wrangler secret put ACCOUNTS_JSON < ~/.config/agy-proxy/accounts.json
npx wrangler deploy
```
*Use your Worker URL directly in Cursor, Windsurf, VS Code, Claude Code, Cline, or Roo Code:*
- **OpenAI**: `https://agy-proxy-edge.<your-subdomain>.workers.dev/v1`
- **Anthropic**: `https://agy-proxy-edge.<your-subdomain>.workers.dev`

#### 🔹 Quick Instant HTTPS Tunnel (`cloudflared`)
If you just want an instant secure public HTTPS URL for your local proxy without deploying anything:
```bash
cloudflared tunnel --url http://127.0.0.1:8000
# Use generated URL: https://<random>.trycloudflare.com/v1 in your clients
```

👉 *See [`cloudflare/README.md`](cloudflare/README.md) for the complete Cloudflare deployment reference.*

---

## 👥 Multi-Account Pool Management & Failover

### Adding Accounts via Web Dashboard
1. Open `http://localhost:8000` in your browser.
2. Click **"➕ Add Google Account"** or **"🔑 Add AI Studio Key"**.
3. Authorize via Google and paste the resulting authorization code/URL or API key.

### Adding Accounts via CLI
```bash
# Log in an OAuth Google account via PKCE browser flow:
uv run python main.py auth login

# Add an AI Studio API key:
uv run python main.py auth add-key "AIzaSy..." --name "My Studio Key"

# List all accounts and remaining quotas:
uv run python main.py auth list
```

### 🔁 Automatic Multi-Candidate Failover Architecture
Antigravity Proxy implements an intelligent failover loop across candidate accounts during generation requests:
1. **Candidate Pool Selection**: When a request arrives, the proxy selects all enabled, healthy accounts with remaining quota for the requested model group.
2. **429 Quota Exhaustion**: If Account A returns `429 Too Many Requests`, the proxy marks Account A rate-limited for 60 seconds and immediately retries the request on Account B without failing the user request.
3. **5xx Server Errors**: If an account encounters upstream `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable`, or `504 Gateway Timeout`, the proxy automatically attempts failover to the next candidate in the pool.
4. **401 Unauthorized**: If an access token expires mid-flight, the proxy automatically forces a token refresh (`refresh_access_token(force=True)`) and retries.

### 🌐 Upstream Proxy Support (`proxy_url` & Environment Variables)
Antigravity Proxy supports routing outbound Google API calls through custom proxies:
- **Per-Account Proxy URL**: Configure a specific `proxy_url` for any account in the Web UI or via REST API. This is persisted in `~/.config/agy-proxy/accounts.json` across server restarts.
- **Global Proxy Variables**: Setting `AGY_UPSTREAM_PROXY` or `ALL_PROXY` (or standard `HTTP_PROXY` / `HTTPS_PROXY`) applies to all account connections automatically.

### 🔄 Switching Active Antigravity CLI & Standalone Sessions
Antigravity Proxy can synchronize your pooled Google accounts with your native system **Antigravity CLI** (`~/.gemini/antigravity-cli/`) and **Antigravity 2.0 Web Agent** (`~/.gemini/jetski-standalone-oauth-token`) sessions without requiring manual re-authentication.

#### 🔹 Via Web Dashboard (Interactive Modal):
1. In the **Google Antigravity Accounts (OAuth)** section, click the **`AGY CLI`** / **`In CLI`** / **`In Standalone`** button on any account card.
2. Select target session scope:
   - **CLI Only** (`~/.gemini/antigravity-cli/`): Updates terminal CLI session.
   - **Standalone Only** (`~/.gemini/jetski-standalone-oauth-token`): Updates Antigravity 2.0 Web Agent.
   - **All (CLI + Standalone)**: Switches both environments simultaneously.
3. Click **"Confirm Switch"** — the proxy writes the official token file, creates a `.bak` backup, and updates status indicators immediately.

#### 🔹 Via CLI Commands:
```bash
# List available OAuth accounts and active statuses:
agy-proxy switch --list

# Switch to a specific account for both CLI and Standalone:
agy-proxy switch "developer@gmail.com"

# Switch an account ONLY for the CLI terminal:
agy-proxy switch "developer@gmail.com" --cli

# Switch an account ONLY for the Standalone Web Agent:
agy-proxy switch "developer@gmail.com" --standalone

# Automatically rotate to the account with the highest remaining quota:
agy-proxy switch --next
```

---

## 🗜 Context Compactor & Auto-Summarization (Token Saver)

Antigravity Proxy features an intelligent **Context Compactor Engine** that continuously monitors conversation length and automatically summarizes older conversation turns when token limits approach threshold.

### 🌟 Why it matters:
- **80% to 98% Token Reduction**: Large 500,000+ token sessions (with full file contents, diffs, and bash outputs) are safely compressed down into a clean ~1,500-token structured context.
- **Zero 400 Context Overflow Errors**: Prevents hitting Google CloudCode's hard limit of `1,048,576 tokens`.
- **Zero Primary Model Quota Wasted**: Compactions and summaries are processed in milliseconds via `gemini-3.1-flash-lite`, using **0% of your primary model quota** (Claude Sonnet/Opus, Gemini Pro).
- **Full History Retention**: Uses a battle-tested 9-section summarization prompt schema, retaining all project architectures, file paths, pending tasks, and user instructions.

### ⚙️ Configuration (Web UI & REST API)
You can configure the compactor dynamically from the Web Dashboard (`http://localhost:8000`) or via REST API:

- **Auto-Summarize Threshold**: Set token threshold from `30,000` to `200,000` tokens (Default: `85,000` tokens).
- **Preserve Last Messages**: Choose how many recent messages to keep uncompressed in full detail (e.g., 4 to 8 messages).
- **Manual `/compact` Command**: Type `/compact` inside supported coding agents (e.g., Claude Code CLI) anytime to trigger instantaneous background compression.

```bash
# Get current compactor settings:
curl http://127.0.0.1:8000/api/context/settings

# Update threshold to 75,000 tokens:
curl -X POST http://127.0.0.1:8000/api/context/settings \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "threshold_tokens": 75000, "keep_last_n": 4}'
```

---

## 🧪 Antigravity Experimental Features & Flags Manager

Antigravity Proxy includes a dedicated **Experimental Features & Flags Manager** (`agy_proxy/experiments.py`) that safely enables next-generation capabilities in Google Antigravity & Antigravity IDE while protecting your environment from toxic or restrictive flags.

### 🌟 Features Unlocked:
- **Autonomous Multi-Agent & Swarms**: Enables `/deepagent`, autonomous agent teams (`enable-agent-team`), native agent swarms (`enable-swarm`, `enable-native-swarm`), Subagent Hub (`enable-subagent-hub`), direct subagent messaging (`enable-subagent-user-messaging`), and Mixture of Agents (`Chat__enable_chat_moa`).
- **Model Context Protocol (MCP)**: Full support for agentic MCP chat (`Chat__enable_chat_agentic_mcp_chat`), MCP server integration (`Chat__enable_mcp_server`), stdio MCP proxies, and non-blocking turn loads.
- **Enhanced IDE UX & Diff View**: Rich inline diff reviews (`DuetAiGeneration__codeGeneration_enable_diff_view`), side-by-side pane views (`DuetAiGeneration__codeGeneration_enable_pane_view`), and reasoning thought inspection & steering (`enable-thought-editing`, `enable-thought-steering-from-selection`).
- **Deep Codebase Awareness & Local RAG**: Enables full-codebase folder selection (`Chat__enable_chat_folder_context_selection`), BM25 local snippet retrieval, open tab inclusion, and 3.5M token context windows.
- **Next-Gen Model Experiment IDs**: Injects and merges 121 verified experiment IDs (including `106544526` for Claude 5.5 and Vertex AI preview) across all accounts in your pool.

### 🛡️ Built-in Toxic Flag Blocklist (Protection against breakage):
Blindly forcing all flags `True` broke features because Google upstream includes restrictive flags:
- `GeminiFreeTier__enable_free_tier`: Forces Free Tier account limitations and disables pro models (strictly kept `false`).
- `disable-search-tools`: Disables workspace search tools (strictly kept `false`).
- `remove-conversation-history`: Deletes conversation history (strictly kept `false`).
- `disable-command-assessor`, feedback blocks, and telemetry polling blocks are protected and sanitized.

### ⚙️ CLI & REST API Management:
```bash
# List all experimental flags and current status:
agy-proxy experiments list

# Force enable a specific flag:
agy-proxy experiments enable enable-deepagent

# Disable a specific flag:
agy-proxy experiments disable enable-deepagent

# Change operating mode (curated [default], all_safe, passthrough):
agy-proxy experiments mode curated

# Reset all overrides back to curated defaults:
agy-proxy experiments reset
```

---

## 🌐 Live Web Search & Google Grounding

Antigravity Proxy natively equips coding agents and IDEs (Cursor, Windsurf, Roo Code, Cline, Claude Code, Aider) with live internet access without needing paid API keys from third-party search providers.

### 🔍 Search Architecture:
1. **Google Grounding (Vertex AI)**: Real-time search indexing directly from Google's search engine.
2. **Multi-Engine Concurrent Fan-Out**: Automatic parallel querying across **DuckDuckGo**, **Bing**, and **Brave** with URL deduplication, domain ranking, and domain filtering (`site:` filters).
3. **Transparent WebSearch Tool Interception**: Automatically handles `WebSearch` and `web_search` tool calls from coding agents and extensions, returning clean, grounded results with citations and URLs.

---

## 📋 Supported Models & Aliases

| Client Request (Alias) | Google Antigravity Backend Model | Reasoning / Thinking Budget | Description |
|---|---|---|---|
| `gemini-3.8-flash-high`, `flash`, `gpt-4o`, `deepseek-r1` | `gemini-3.8-flash-high` | **HIGH** | ⚡ **Default Flagship**: Gemini 3.8 Flash with full reasoning |
| `gemini-3.8-flash-medium` | `gemini-3.8-flash-medium` | **MEDIUM** | ⚖️ Gemini 3.8 Flash with balanced reasoning budget |
| `gemini-3.8-flash-low` | `gemini-3.8-flash-low` | **LOW** | ⚡ Gemini 3.8 Flash with low reasoning budget |
| `gemini-3.8-flash-tiered` | `gemini-3.8-flash-tiered` | Dynamic | 🔄 Gemini 3.8 Flash with tiered dynamic thinking |
| `gemini-3.7-flash-high`, `gemini-3.7-flash` | `gemini-3.7-flash-high` | **HIGH** | ⚡ Gemini 3.7 Flash with extended reasoning |
| `gemini-3.7-flash-medium`, `gemini-3.7-flash-low` | `gemini-3.7-flash-*` | MEDIUM / LOW | ⚖️ Gemini 3.7 Flash with balanced/low thinking |
| `gemini-3.1-pro-high`, `gemini-3.1-pro`, `pro` | `gemini-3.1-pro-high` | **HIGH** | 🧠 Flagship Pro model for complex logic & math |
| `gemini-3.1-pro-low` | `gemini-3.1-pro-low` | **LOW** | 🧠 Gemini 3.1 Pro with minimal reasoning |
| `gemini-3.1-flash-lite`, `gpt-4o-mini`, `flash-lite` | `gemini-3.1-flash-lite` | Disabled (0) | 💡 Ultra-fast lightweight model (Background tasks & Compactor) |
| `claude-sonnet-5-5-high`, `claude-5-5`, `claude-sonnet-5-5` | `claude-sonnet-5-5-high` | **HIGH** | 🚀 Claude Sonnet 5.5 (1M context, 128k output, Vertex AI) |
| `claude-sonnet-5-5-medium`, `claude-sonnet-5-5-low` | `claude-sonnet-5-5-*` | MEDIUM / LOW | ⚡ Claude Sonnet 5.5 with medium/light reasoning (1M context) |
| `claude-opus-5-5-high`, `claude-opus-5-5` | `claude-opus-5-5-high` | **HIGH** | 🔬 Claude Opus 5.5 flagship deep reasoning (1M context) |
| `claude-opus-5-5-medium`, `claude-opus-5-5-low` | `claude-opus-5-5-*` | MEDIUM / LOW | 🔬 Claude Opus 5.5 with medium/light reasoning (1M context) |
| `claude-sonnet-4-6`, `claude-3-7-sonnet`, `claude-3-5-sonnet`, `claude` | `claude-sonnet-4-6` | Configurable | 🚀 Claude Sonnet 4.6 backend (with role sanitization) |
| `claude-opus-4-6-thinking`, `claude-3-opus` | `claude-opus-4-6-thinking` | **HIGH** | 🔬 Claude Opus 4.6 with reasoning thinking process |
| `gpt-oss-120b-medium`, `gpt-oss-120b` | `gpt-oss-120b-medium` | MEDIUM | 🌐 Open Source 120B model |
| `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.5` | `gemini-3.8-flash-high` | **HIGH** | 🤖 Codex CLI Flagship Reasoning Aliases |
| `gpt-5.6-terra` | `gemini-3.8-flash-medium` | **MEDIUM** | 🤖 Codex CLI Balanced Reasoning Alias |
| `gpt-5.6-luna`, `gpt-5.4-mini` | `gemini-3.1-flash-lite` | Disabled (0) | 🤖 Codex CLI Lightweight Fast Aliases |
| `gpt-5.2` | `gemini-3.7-flash-high` | **HIGH** | 🤖 Codex CLI Gemini 3.7 Alias |
| `o1`, `o1-mini`, `o3-mini` | `gemini-3.8-flash-high` | **HIGH** | 🎯 OpenAI Reasoning Aliases |

---

## 💻 SDK Integration Examples

### Python (Official OpenAI SDK)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="dummy"
)

response = client.chat.completions.create(
    model="gemini-3.8-flash-high",
    messages=[{"role": "user", "content": "Explain how quantum computers work in simple terms."}],
    stream=True
)

for chunk in response:
    if hasattr(chunk.choices[0].delta, "reasoning_content") and chunk.choices[0].delta.reasoning_content:
        print(chunk.choices[0].delta.reasoning_content, end="", flush=True)
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Python (Official Anthropic SDK)
```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://127.0.0.1:8000",
    api_key="dummy"
)

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello! Describe your capabilities."}]
)

print(message.content[0].text)
```

---

## 📋 Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Port for the proxy server to listen on. |
| `HOST` | `127.0.0.1` | Network interface to bind to (`0.0.0.0` for LAN access). |
| `PROXY_API_KEY` / `AGY_PROXY_API_KEY` | *(None)* | If set, requires `Authorization: Bearer <key>` header on all requests. |
| `CLOUDFLARE_UPSTREAM_URL` | *(None)* | Routes Google CloudCode API requests via deployed Cloudflare Worker for Geo-Bypass. |
| `AGY_UPSTREAM_PROXY` / `ALL_PROXY` | *(None)* | Corporate/SOCKS5/HTTP upstream proxy URL applied to all Google API sessions. |
| `HTTP_PROXY` / `HTTPS_PROXY` | *(None)* | Standard HTTP/HTTPS proxy URLs for Python HTTP client. |
| `AGY_RATE_LIMIT_COOLDOWN` | `0` | Rate-limit cooldown in seconds when HTTP 429 occurs (0 = instant pool failover). |
| `AGY_TOKEN_FILE` / `ANTIGRAVITY_TOKEN_FILE` | *(Auto)* | Custom path to primary Antigravity CLI token file. |
| `AGY_PROXY_COMPACT_ENABLED` | `false` | Enable automatic context compactor engine. |
| `AGY_PROXY_COMPACT_THRESHOLD` | `85000` | Token threshold to trigger context auto-compaction. |
| `AGY_PROXY_KEEP_LAST_N` | `6` | Number of recent messages to preserve uncompacted. |

---

## 🔒 Configuration & Data Security

- 📁 **Account Pool Configuration**: `~/.config/agy-proxy/accounts.json`
- 🔍 **Zero-Config Session Auto-Discovery**: The proxy automatically discovers existing local tokens from:
  - `~/.gemini/antigravity-cli/antigravity-oauth-token`
  - `~/.gemini/antigravity-ide/antigravity-oauth-token`
  - `~/.gemini/jetski-standalone-oauth-token`
- 🛡️ All credentials and tokens are stored **strictly locally** on your machine with strict `0600` permissions.

---

## 🤖 Repository Automation & Issue Lifecycle

To keep the project clean and focused, an automated GitHub Actions workflow ([`.github/workflows/close-inactive-issues.yml`](.github/workflows/close-inactive-issues.yml)) monitors repository activity:
- Issues and pull requests inactive for **7 days** are automatically marked as `stale`.
- If no response or activity occurs for an additional **7 days**, the issue or pull request is automatically closed.
- Any comment or commit immediately un-stales the thread.

---

## 📄 License

Distributed under the **GNU General Public License v3.0 (GPLv3)**. See [`LICENSE`](LICENSE) for more information.
