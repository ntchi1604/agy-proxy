# 🌐 Cloudflare Edge Proxy & Serverless Guide

This directory contains everything you need to run **Antigravity Proxy** through **Cloudflare** for:
1. 🌍 **Geo-Bypass**: Bypass regional IP blocks on Google CloudCode & Gemini APIs with 0% VPN overhead.
2. ☁️ **100% Serverless Mode**: Run the proxy 24/7 on Cloudflare Edge without keeping your PC or server turned on.
3. 🔒 **Public HTTPS Access**: Connect from Cursor, Windsurf, Claude Code, or mobile devices anywhere via Cloudflare Tunnels or Worker URLs.

---

## ⚡ Architecture Modes

You can use Cloudflare in two ways:

| Mode | Where Accounts are Stored | Requires Running Local PC? | Best For |
|---|---|---|---|
| **Mode 1: Upstream Gateway (Hybrid)** | `~/.config/agy-proxy/accounts.json` on local PC | Yes | Local development with Web Dashboard, automatic local token management |
| **Mode 2: 100% Serverless Edge** | `ACCOUNTS_JSON` secret in Cloudflare | **No** (runs 24/7 in the cloud) | Team sharing, accessing from multiple laptops/phones with zero local server |

---

## 🚀 Setup Guide

### Mode 1: Upstream Gateway / Geo-Bypass (Recommended for local dev)

In this mode, `agy-proxy` runs on your computer and routes all outgoing Google API traffic through your Cloudflare Worker to bypass regional blocks.

#### 1. Deploy the Worker
```bash
cd cloudflare
npx wrangler deploy
```
*Wrangler will output your worker URL, e.g.: `https://agy-proxy-edge.<your-subdomain>.workers.dev`*

#### 2. Start `agy-proxy` with the Worker URL
```bash
# Using CLI flag:
agy-proxy --port 8000 --cloudflare-url "https://agy-proxy-edge.<your-subdomain>.workers.dev"

# OR via environment variable:
export CLOUDFLARE_UPSTREAM_URL="https://agy-proxy-edge.<your-subdomain>.workers.dev"
agy-proxy --port 8000
```

---

### Mode 2: 100% Serverless Standalone Mode (No PC needed)

In this mode, the Cloudflare Worker runs the entire proxy logic, token refreshes, and multi-account failover directly in the cloud.

#### 1. Upload your accounts to Cloudflare Secrets
Run this single command from your local machine to upload your existing account pool:
```bash
cd cloudflare
npx wrangler secret put ACCOUNTS_JSON < ~/.config/agy-proxy/accounts.json
```
*(Supports standard `accounts.json`, `api_keys.json`, or export files from `/api/accounts/export`)*

#### 2. (Optional) Set an API Key for security
```bash
npx wrangler secret put PROXY_API_KEY
# Enter your secret API key when prompted
```

#### 3. Deploy
```bash
npx wrangler deploy
```

#### 4. Use your Serverless URL in your IDE / CLI
You can now directly use:
- **OpenAI Base URL**: `https://agy-proxy-edge.<your-subdomain>.workers.dev/v1`
- **Anthropic Base URL**: `https://agy-proxy-edge.<your-subdomain>.workers.dev`
- **API Key**: `dummy` (or your `PROXY_API_KEY`)
- **Default Model**: `gemini-3.8-flash-high`
- **Supported Models**: `gemini-3.8-flash-high`, `gemini-3.8-flash-medium`, `claude-sonnet-4-6`, `claude-3-7-sonnet`, `claude-3-5-sonnet`, `gpt-4o`, `gpt-4o-mini`, `o1`, `deepseek-r1`

---

## 💡 Key Features in v2.2.0

- **Upstream User-Agent**: Updated to `antigravity/hub/2.19.1` matching official client telemetry.
- **Multi-Account Failover Loop**: Automatically rotates and fails over to healthy accounts on `429 Too Many Requests`, `401 Unauthorized` (with token refresh), or `5xx Server Error`.
- **Role Sanitization**: Message roles are strictly mapped to `user` or `model` (lowercase) and system instructions are extracted into `systemInstruction`, preventing CloudCode Error 500 on Claude models.
- **Claude Code CLI Compatibility**: Full support for Claude Code endpoints (`/api/hello`, `/api/claude_cli/bootstrap`, `/api/claude_code_penguin_mode`, `/api/web/domain_info`, `/v1/messages`).
- **OpenAI Responses API**: Compatible with Codex CLI and OpenAI `/v1/responses` endpoints.
- **Disabled Accounts Filter**: Ignores disabled accounts (`enabled: false`) when parsing credentials.

---

## 🚇 Quick Public HTTPS Tunnel (`cloudflared`)

If you run `agy-proxy` locally and just want a quick public HTTPS URL without deploying anything:

```bash
# Start an instant tunnel
cloudflared tunnel --url http://127.0.0.1:8000
```

`cloudflared` will generate a public URL like:
`https://random-name.trycloudflare.com`

You can use `https://random-name.trycloudflare.com/v1` in Cursor, Windsurf, or Claude Code on any external device!

---

## 📋 Environment Variables Reference

| Variable | Scope | Description |
|---|---|---|
| `CLOUDFLARE_UPSTREAM_URL` | Local `agy-proxy` | URL of your deployed Cloudflare Worker to route traffic through. |
| `ACCOUNTS_JSON` | Cloudflare Worker Secret | JSON string of account credentials for 100% serverless edge mode. |
| `PROXY_API_KEY` | Local or Worker | Secret key required in client request headers (`Authorization: Bearer <key>`). |
| `HTTP_PROXY` / `HTTPS_PROXY` | Local `agy-proxy` | Standard proxy URL for Python `httpx`. |
