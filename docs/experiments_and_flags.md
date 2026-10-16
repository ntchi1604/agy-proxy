# 🧪 Antigravity Experimental Features & Flags Manager

Safely unlock hidden developer features and experimental capabilities in Antigravity while shielding against toxic internal Google flags.

---

## 🌟 Unlocked Features

By default, `agy-proxy` curates and activates verified stable experimental features:

- ⚔️ **Battle Mode (`enable-battle-mode`)**: Run multiple models in parallel on the same prompt to compare answers side-by-side.
- 🤖 **Autonomous Mode (`labs-autonomous-mode`, `jetski-autonomous-mode`)**: Grants autonomous execution without repeated confirmation prompts for safe tasks.
- 💬 **Inline Actions (`labs-inline-actions`)**: Floating toast notification cards to answer questions and grant permissions without switching tabs.
- 🧠 **Thought Steering & Editing (`enable-thought-editing`, `enable-thought-steering-from-selection`)**: Edit or redirect model internal reasoning chains directly in the chat UI.
- 📁 **File Explorer Tab (`enable-file-explorer-tab`)**: Native side panel file tree inside Web Hub.
- 🪟 **Split View (`enable-split-view`)**: Side-by-side multi-conversation panes.
- 🔍 **Conversation Search V2 (`enable-conversation-search-v2`)**: Fast full-text search across all past chat sessions.

---

## 🛡️ Toxic Flag Blocklist (Protection against breakage)

Certain experimental flags built into Google's internal code require Google corporate infrastructure (`blaze run`, Google3 Piper depot paths, internal microservices). Enabling them outside of Google breaks the application.

`agy-proxy` automatically shields your installation by blocklisting:
- `enable-agent-team`: Calls missing `blaze run //third_party/jetski/...` scripts.
- `enable-concierge-agent`, `labs-concierge-agent`: Calls missing `/google/data/.../concierge_main.par` binaries.
- `enable-piper-depot`: Crashes when Google's internal Piper VCS is absent.
- `enable-internal-telemetry`: Blocks hanging internal analytics network calls.

---

## ⚙️ CLI & REST API Management

```bash
# List all experimental flags and current status:
agy-proxy flags

# Force enable a specific flag:
agy-proxy flags --enable "enable-battle-mode"

# Disable a specific flag:
agy-proxy flags --disable "enable-thought-editing"

# Change operating mode (curated [default], all_safe, passthrough):
agy-proxy flags --mode curated

# Reset all overrides back to curated defaults:
agy-proxy flags --reset
```

---

[← Back to Main README](../README.md)
