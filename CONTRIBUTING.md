# Contributing to Antigravity Proxy

Thank you for your interest in contributing to **Antigravity Proxy**! 🎉

We welcome contributions of all kinds: bug fixes, new features, model mappings, client integrations, documentation improvements, and feedback.

---

## 🚀 Getting Started

### 1. Fork and Clone
```bash
git clone https://github.com/kqlio67/agy-proxy.git
cd agy-proxy
```

### 2. Environment Setup
We recommend using [`uv`](https://github.com/astral-sh/uv) or standard Python 3.10+:

```bash
# Using uv (fastest):
uv sync

# Or using standard venv:
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Running the Server Locally
```bash
./start_proxy.sh --port 8000
# or: uv run python main.py --port 8000
```

Open [http://localhost:8000](http://localhost:8000) to view the Web UI Dashboard.

---

## 🧪 Running Tests

Before submitting changes, ensure the entire test suite passes:

```bash
# Run tests with pytest (recommended):
uv run pytest

# Or run the comprehensive test script:
uv run python test_proxy.py
```

---

## 📝 Development Guidelines

1. **Clean Code & Idiom:** Write clean, asynchronous code that matches surrounding patterns.
2. **Multi-Account Safety & Failover:** Ensure changes do not break multi-account concurrency (`asyncio.Lock()` per session) or the 429/5xx multi-candidate failover loop.
3. **Role Normalization & Converters:** Any changes to protocol converters (`agy_proxy/converters/`) must preserve role lowercase sanitization (`user`/`model`), thought signature tracking, schema flattening (`anyOf`/`oneOf`/`allOf`), and tool pairing integrity.
4. **No Hardcoded Secrets:** Never commit API keys, OAuth tokens, or sensitive credentials.

---

## 📦 Pull Request Process

1. **Create a Feature Branch:**
   ```bash
   git checkout -b feature/my-cool-feature
   ```
2. **Make your changes** and verify all unit tests pass (`uv run pytest`).
3. **Commit with Clear Messages:** Follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat: ...`, `fix: ...`, `docs: ...`).
4. **Push and Open a Pull Request** against the `main` branch.

---

## 🤖 Stale Issues & PR Management

To maintain repository health, an automated GitHub Actions workflow (`.github/workflows/close-inactive-issues.yml`) manages inactive threads:
- **7 Days Inactive**: Open issues or pull requests with no activity for 7 days are automatically labeled as `stale`.
- **7 Days Grace Period**: If an issue or PR remains inactive for another 7 days after receiving the `stale` label, it will be automatically closed.
- Commenting or pushing new commits immediately removes the `stale` label and resets the timer.

---

## 💬 Community & Questions

- If you encounter a bug or have a feature request, please open a [GitHub Issue](https://github.com/kqlio67/agy-proxy/issues).
- Be respectful and constructive (see [Code of Conduct](CODE_OF_CONDUCT.md)).
