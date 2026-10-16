# 🌐 Cloudflare Edge Worker & Remote Access

Run `agy-proxy` remotely, bypass regional restrictions (Geo-Bypass), or host a 100% serverless edge instance on Cloudflare Workers.

---

## ⚡ Mode 1: Geo-Bypass Upstream Gateway (Recommended)

If your local IP is blocked from accessing Google CloudCode or Generative Language APIs:

1. Deploy the worker to your Cloudflare account in 1 command:
   ```bash
   cd cloudflare
   npm install && npx wrangler deploy
   ```
2. Start your local `agy-proxy` pointing through the Cloudflare worker:
   ```bash
   agy-proxy --upstream-proxy "https://my-worker.my-account.workers.dev"
   ```
   Or set the environment variable:
   ```bash
   export AGY_UPSTREAM_PROXY="https://my-worker.my-account.workers.dev"
   ```

---

## ☁️ Mode 2: 100% Serverless Edge Mode (24/7 Cloud)

Run `agy-proxy` entirely on Cloudflare Workers without keeping your PC powered on:

1. Configure your pooled accounts into Cloudflare Secrets:
   ```bash
   agy-proxy export-accounts | npx wrangler secret put ACCOUNTS_JSON
   ```
2. Deploy the serverless edge worker:
   ```bash
   npx wrangler deploy
   ```
3. Point your IDE or Claude Code directly to your Worker endpoint:
   ```
   https://my-worker.my-account.workers.dev/v1
   ```

---

## 🔒 Quick Instant HTTPS Tunnel (`cloudflared`)

Expose your local `agy-proxy` to the internet with secure SSL in 1 command without opening ports:

```bash
# Start Cloudflare Tunnel:
cloudflared tunnel --url http://localhost:8000
```

Use the generated temporary URL (e.g. `https://<random>.trycloudflare.com/v1`) in your mobile devices, remote servers, or external clients.

---

[← Back to Main README](../README.md)
