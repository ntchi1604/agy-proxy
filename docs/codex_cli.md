# ⌨️ OpenAI Codex CLI Integration Guide

Integrate OpenAI's **Codex CLI (v0.150+)** directly with `agy-proxy` to leverage high-speed Antigravity models.

---

## 🚀 Integration Methods

### Option A — 1-Click Launcher (`run_codex.sh`)

Use the built-in helper script to launch Codex CLI with interactive model selection:

```bash
# Interactive mode with Antigravity model catalog:
./run_codex.sh

# Launch directly with a specific model:
./run_codex.sh -m gemini-3.8-flash-high
./run_codex.sh -m claude-sonnet-4-6
```

---

### Option B — Ephemeral Run (`agy-proxy codex`)

Run Codex through the proxy on the fly without modifying your personal configuration files:

```bash
# Launches codex through the proxy without modifying ~/.codex/config.toml:
agy-proxy codex --port 8000 --model gemini-3.8-flash-high
```

---

### Option C — Persistent Configuration (`~/.codex/config.toml`)

Automatically update your global Codex settings:

```bash
# Configure ~/.codex/config.toml and inject the Antigravity model catalog:
agy-proxy setup-codex --port 8000 --model gemini-3.8-flash-high

# Or restore original config at any time:
agy-proxy restore-codex
```

### Manual Configuration Example
If editing `~/.codex/config.toml` manually:

```toml
[client]
api_base = "http://127.0.0.1:8000/v1"
api_key = "dummy"
model = "gemini-3.8-flash-high"
```

---

[← Back to Main README](../README.md)
