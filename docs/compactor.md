# 🗜 Context Compactor & Auto-Summarization (Token Saver)

Prevent context-window overflows and save **80% to 95%+ tokens** on long-running coding conversations.

---

## 🌟 Why it matters

- **Google Hard Limit Prevention**: Google's upstream models enforce a strict hard limit of 1,048,576 tokens per conversation, failing with `HTTP 400 Bad Request` once exceeded.
- **Cost & Quota Efficiency**: Compacting older message history into structured semantic summaries dramatically reduces input token consumption and latency.
- **Native Command Interception**: Intercepts `/compact` and `/autocompact` commands issued by coding agents (Claude Code, Antigravity Agent, Roo Code).

---

## ⚙️ How It Works

When conversation history crosses your configured token threshold (default: 80,000 tokens):
1. Older conversation turns are fed to ultra-fast `gemini-3.1-flash-lite`.
2. Compressed into a standardized 9-section markdown summary:
   - Primary goals & tasks
   - Architecture & directory layout
   - Files inspected & modified
   - Key decisions & constraints
   - Test results & verification status
3. The latest messages (active working context) are preserved verbatim.
4. Seamlessly replaces hundreds of verbose turns with a compact checkpoint.

---

## ⚙️ Configuration (Web UI & REST API)

Adjust compaction parameters in the Web Dashboard (`http://127.0.0.1:8000`) or via REST API:

```bash
# Get current compactor settings:
curl -s http://127.0.0.1:8000/api/compactor/settings

# Update threshold to 75,000 tokens:
curl -X POST http://127.0.0.1:8000/api/compactor/settings \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "token_threshold": 75000,
    "model": "gemini-3.1-flash-lite"
  }'
```

---

[← Back to Main README](../README.md)
