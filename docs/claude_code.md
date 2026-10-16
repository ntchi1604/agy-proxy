# 🤖 Claude Code CLI Integration Guide

Integrate Anthropic's official **Claude Code CLI** with `agy-proxy` to use powerful Gemini 3.8 and Claude models with zero cost and high quotas.

---

## 🚀 1-Click Launch Scripts

The repository includes pre-built wrapper scripts that configure the environment and launch Claude Code instantly.

### Linux / macOS / Termux (`run_claude.sh`)

```bash
# 1-Click Launch:
./run_claude.sh

# Launch on custom proxy port:
./run_claude.sh -p 8080

# Launch with a specific model (e.g. Claude Sonnet 4.6 or Gemini 3.8):
./run_claude.sh -m claude-sonnet-4-6
./run_claude.sh -m gemini-3.8-flash-high

# Pass direct arguments to Claude Code CLI:
./run_claude.sh -p 8000 -- --dangerously-skip-permissions "Explain this codebase"
```

### Windows (`run_claude.bat`)

```cmd
:: Command Prompt:
run_claude.bat
run_claude.bat -p 8080 -m gemini-3.8-flash-high
```

---

## ⚙️ Persistent Configuration via CLI (`setup-claude`)

Automatically configure your local `~/.claude/settings.json` so that running standard `claude` commands always routes through `agy-proxy`:

```bash
# Configure Claude Code settings:
agy-proxy setup-claude --port 8000 --model claude-sonnet-4-6

# Check status:
claude "Hello from agy-proxy!"

# Restore original Claude Code configuration:
agy-proxy restore-claude
```

---

## 🛠 Manual Launch (Direct Environment Variables)

If you prefer setting environment variables manually without wrapper scripts:

### Linux / macOS
```bash
ANTHROPIC_BASE_URL="http://127.0.0.1:8000" \
ANTHROPIC_API_KEY="dummy" \
ANTHROPIC_MODEL="gemini-3.8-flash-high" \
claude
```

### Windows PowerShell
```powershell
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
$env:ANTHROPIC_API_KEY="dummy"
$env:ANTHROPIC_MODEL="gemini-3.8-flash-high"
claude
```

### Windows Command Prompt
```cmd
set ANTHROPIC_BASE_URL=http://127.0.0.1:8000
set ANTHROPIC_API_KEY=dummy
set ANTHROPIC_MODEL=gemini-3.8-flash-high
claude
```

---

## 🎭 Claude Role Sanitization & Error 500 Prevention

When using Claude models through upstream Google CloudCode proxies, standard Claude message histories frequently trigger `HTTP 500 Internal Server Error` due to strict role validation.

`agy-proxy` incorporates deep sanitization:
- **Role Normalization**: Normalizes all message roles (`user`, `context` -> `user`; `model`, `assistant` -> `model` strictly in lowercase).
- **System Instruction Extraction**: Automatically separates system instructions into `systemInstruction` parameters compatible with upstream Google endpoints.
- **Retry-After Headers**: Injects `Retry-After: 2` headers to avoid multi-minute exponential backoff retry locks in Claude Code.

---

[← Back to Main README](../README.md)
