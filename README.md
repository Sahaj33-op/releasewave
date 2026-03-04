<div align="center">

# 🌊 ReleaseWave

### AI-Powered Changelog Generator That Actually Works

**Reads real code diffs. Works on messy commits. Generates 3 audience-targeted changelogs in one command.**

[![PyPI version](https://img.shields.io/pypi/v/releasewave?color=blue&label=PyPI)](https://pypi.org/project/releasewave/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/sahaj/releasewave?style=social)](https://github.com/sahaj/releasewave)

[Quick Start](#-quick-start) · [Why ReleaseWave?](#-why-releasewave) · [GitHub Action](#-github-action) · [Configuration](#-configuration) · [Models](#-models)

</div>

---

## ⚡ Quick Start

```bash
# Install
pip install releasewave

# Generate changelogs (zero config!)
releasewave generate v1.0.0 v1.1.0

# That's it. Three files appear:
# CHANGELOG-developer.md  — Technical changelog
# RELEASE-NOTES.md        — User-facing notes
# TWEET.txt               — Tweet-sized announcement
```

## 🤔 Why ReleaseWave?

Every existing changelog tool has the same fatal flaw: **they require clean, conventional commit messages.**

Real-world repos look like this:

```
fix
wip
update stuff  
lol this works now
asdfghjkl
merge branch 'main' of github.com/...
```

**ReleaseWave doesn't care.** It reads the actual code diffs, not just the commit messages.

| Feature | git-cliff | conventional-changelog | release-please | **ReleaseWave** |
|---|:-:|:-:|:-:|:-:|
| Works on messy commits | ❌ | ❌ | ❌ | ✅ |
| Reads actual code diffs | ❌ | ❌ | ❌ | ✅ |
| Multi-audience output | ❌ | ❌ | ❌ | ✅ |
| Zero config | ❌ | ❌ | ❌ | ✅ |
| Monorepo support | ⚠️ | ⚠️ | ⚠️ | ✅ |
| GitHub Action | ❌ | ❌ | ✅ | ✅ |

## 📋 Three Outputs, One Command

ReleaseWave generates **three distinct changelogs** per run:

### 🔧 Developer Changelog

Technical, precise, with file paths and commit refs:

```markdown
## ✨ Features
- **Add WebSocket support for real-time updates** — New `ws_handler.py` 
  implements bidirectional communication via `websockets` library. 
  Affected: `src/ws_handler.py`, `src/app.py` (abc123d)

## 🐛 Bug Fixes  
- **Fix race condition in connection pooling** — Mutex lock added to 
  `pool.acquire()` preventing double-allocation under load. (def456a)
```

### 📋 User Release Notes

Plain English, impact-focused, no jargon:

```markdown
## 🎯 Highlights
- **Real-time updates!** Your dashboard now updates instantly — 
  no more refreshing the page.
- **Faster under heavy load** — We fixed an issue that could cause 
  slowdowns when many users connected simultaneously.
```

### 🐦 Tweet Announcement

```
🌊 v1.1.0 is here! Real-time WebSocket updates, faster connection pooling, 
and 3 new API endpoints. Upgrade now for instant dashboard updates ⚡
```

## 🚀 GitHub Action

Drop this into your workflow — changelogs generate automatically on every release:

```yaml
# .github/workflows/release-notes.yml
name: Generate Release Notes
on:
  release:
    types: [published]

jobs:
  changelog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: sahaj/releasewave@v1
        with:
          from_ref: ${{ github.event.release.previous_tag }}
          to_ref: ${{ github.event.release.tag_name }}
          api_key: ${{ secrets.GEMINI_API_KEY }}
          update_changelog: 'true'
```

See [.github/workflows/release-notes.yml](.github/workflows/release-notes.yml) for a complete example.

## 🔧 CLI Reference

```bash
# Basic usage
releasewave generate <from_ref> <to_ref>

# Specify model
releasewave generate v1.0 v1.1 --model gpt-4o-mini

# Custom output directory
releasewave generate v1.0 v1.1 --output ./docs/releases

# Only developer + tweet (skip user notes)
releasewave generate v1.0 v1.1 --audiences developer,tweet

# Update existing CHANGELOG.md
releasewave generate v1.0 v1.1 --update-changelog

# Export full analysis as JSON
releasewave generate v1.0 v1.1 --json

# Quiet mode (just write files, no stdout)
releasewave generate v1.0 v1.1 --quiet

# Different repo path
releasewave generate v1.0 v1.1 --repo /path/to/repo

# Initialize config file
releasewave init

# Show recommended models
releasewave models
```

**Alias:** You can use `rwave` instead of `releasewave`:

```bash
rwave generate v1.0 v1.1
```

## ⚙️ Configuration

ReleaseWave works with **zero configuration**, but you can customize everything via `.rwave.yml`:

```bash
# Generate a config file
releasewave init
```

```yaml
# .rwave.yml
llm:
  model: gemini/gemini-2.0-flash    # Any LiteLLM-supported model
  temperature: 0.3
  max_retries: 3

output:
  audiences: [developer, user, tweet]
  update_changelog: true
  directory: ./docs

filters:
  exclude_patterns:
    - "*.lock"
    - "package-lock.json"
    - "node_modules/*"

# Help the LLM understand your project
project_context: "A React dashboard with a FastAPI backend"
custom_prompt: "Pay special attention to API breaking changes"
```

### Configuration Precedence

1. **CLI flags** (highest priority)
2. **Environment variables** (`RWAVE_MODEL`, `RWAVE_API_KEY`)
3. **Config file** (`.rwave.yml`)
4. **Defaults** (lowest priority)

## 🤖 Models

ReleaseWave supports **any model** via [LiteLLM](https://docs.litellm.ai/):

| Model | Provider | Cost | Quality |
|---|---|---|---|
| `gemini/gemini-2.0-flash` | Google | 💚 Very cheap | ⭐⭐⭐⭐ |
| `gpt-4o-mini` | OpenAI | 💚 Cheap | ⭐⭐⭐⭐ |
| `gpt-4o` | OpenAI | 💛 Moderate | ⭐⭐⭐⭐⭐ |
| `claude-sonnet-4-20250514` | Anthropic | 💛 Moderate | ⭐⭐⭐⭐⭐ |
| `ollama/llama3` | Local | 💚 Free | ⭐⭐⭐ |
| `openrouter/<model>` | OpenRouter | 💛 Varies | ⭐⭐⭐⭐ |

Set your API key:

```bash
# Google Gemini (default, cheapest)
export GEMINI_API_KEY="your-key"

# OpenAI
export OPENAI_API_KEY="your-key"

# Anthropic
export ANTHROPIC_API_KEY="your-key"

# Or use the universal key
export RWAVE_API_KEY="your-key"

# Local Ollama — no key needed!
releasewave generate v1.0 v1.1 --model ollama/llama3
```

## 📦 Monorepo Support

ReleaseWave automatically detects monorepo structures and generates per-package changelogs:

```
my-monorepo/
├── packages/
│   ├── api/          ← Detected as @myapp/api
│   ├── web/          ← Detected as @myapp/web
│   └── shared/       ← Detected as @myapp/shared
├── package.json      ← Workspace config
└── .rwave.yml
```

Supports: npm/yarn/pnpm workspaces, Python packages, Cargo workspaces, Go modules, and more.

## 🏗️ How It Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Git Refs    │────▶│  Diff        │────▶│  Chunker    │
│  Resolution  │     │  Extraction  │     │  (Token     │
│              │     │              │     │   Safety)   │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
┌─────────────┐     ┌──────────────┐     ┌──────▼──────┐
│  3 Audience  │◀────│  LLM         │◀────│  Commit     │
│  Changelogs  │     │  Analysis    │     │  Log +      │
│              │     │              │     │  Diffs      │
└─────────────┘     └──────────────┘     └─────────────┘
```

1. **Ref Resolution** — Validates and resolves git tags/branches/SHAs
2. **Diff Extraction** — Runs `git diff`, filters noise (lockfiles, binaries), respects size limits
3. **Chunking** — Splits large diffs into token-safe chunks, grouped by directory
4. **LLM Analysis** — Sends diffs + commits to LLM, receives categorized changes
5. **Audience Rendering** — Three separate prompts for developer, user, and tweet audiences
6. **Output** — Writes markdown files, optionally updates CHANGELOG.md

## 🛡️ Edge Cases Handled

- **Binary files** → Noted as "binary file changed", not sent to LLM
- **Massive diffs (1000+ files)** → Auto-chunked by directory, merged after analysis
- **LLM API failure** → Graceful fallback to commit-message-only mode
- **No commits in range** → Clear error with suggested correct syntax
- **Rate limiting** → Exponential backoff with configurable retry count
- **Lock files & generated code** → Excluded by default via filters

## 🤝 Contributing

Contributions welcome! Here's how to set up the dev environment:

```bash
# Clone
git clone https://github.com/sahaj/releasewave.git
cd releasewave

# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy releasewave/
```

## 📄 License

MIT — do whatever you want with it.

---

<div align="center">

**Built with ❤️ by [Sahaj](https://github.com/sahaj)**

If ReleaseWave saves you time, consider [giving it a star ⭐](https://github.com/sahaj/releasewave)

</div>
