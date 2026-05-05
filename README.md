<div align="center">

# 🌊 ReleaseWave

**AI-powered release notes, changelogs, and promotional tweets straight from your Git history.**

[![PyPI Version](https://img.shields.io/pypi/v/releasewave.svg)](https://pypi.org/project/releasewave/)
[![Python Versions](https://img.shields.io/pypi/pyversions/releasewave.svg)](https://pypi.org/project/releasewave/)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/sahaj33-op/releasewave/release-notes.yml?branch=main)](https://github.com/sahaj33-op/releasewave/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**[Documentation](#usage) • [GitHub Action](#github-action) • [Configuration](#configuration) • [Contributing](#contributing)**

</div>

---

## ⚡️ What is ReleaseWave?

Writing release notes is tedious. **ReleaseWave** automates the process by acting as an agentic pipeline between your repository and Large Language Models. 

It reads your local Git history, smartly chunks large diffs to avoid token limits, and passes them through an LLM to generate polished release artifacts—whether you need a highly technical developer changelog, user-friendly release notes, or a hype tweet for your next launch.

### ✨ Key Features
*   **🧠 Smart Context Chunking:** Handles massive pull requests and diffs without overflowing LLM context windows.
*   **🔌 Dual Functionality:** Run it locally as a Python CLI or plug it directly into your CI/CD pipeline as a GitHub Action.
*   **🎨 Highly Customizable:** Define your own prompts, models, and formatting rules via a simple `.rwave.yml` file.
*   **🔒 Domain Isolated:** Built with a clean architecture that strictly separates git extraction, data processing, and LLM inference.

---

## 🚀 Quick Start

### Installation

Install ReleaseWave via `pip`:

```bash
pip install releasewave
```

*Requires Python 3.8+*

### CLI Usage

Navigate to your git repository and run the CLI. By default, ReleaseWave will analyze the latest commits and generate standard release notes.

```bash
# Generate release notes for the latest tag
rwave generate

# Generate specific outputs
rwave generate --output tweet
rwave generate --output changelog --since v1.0.0
```

---

## 🤖 GitHub Action

Automate your release process by adding ReleaseWave directly to your GitHub Actions.

Create a file at `.github/workflows/release-notes.yml`:

```yaml
name: Generate Release Notes

on:
  release:
    types: [created]

jobs:
  releasewave:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0 # Required to extract git history

      - name: Run ReleaseWave
        uses: sahaj33-op/releasewave@main
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
        with:
          output-type: 'release-notes'
          publish-to-pr: true
```

---

## ⚙️ Configuration

ReleaseWave is highly configurable. Create a `.rwave.yml` file in the root of your repository to override defaults. 

*(See the `.rwave.yml.example` file for a full list of options).*

```yaml
# .rwave.yml
model:
  provider: openai # or anthropic, gemini, etc.
  name: gpt-4-turbo
  temperature: 0.7

output:
  format: markdown
  destinations:
    - examples/CHANGELOG-developer.md
    - examples/RELEASE-NOTES.md

chunking:
  max_tokens: 8000
  strategy: semantic
```

---

## 📂 Architecture Overview

ReleaseWave is built as a modular pipeline to ensure stability and extensibility:

1.  **Extraction (`git_ops.py`):** Pulls raw diffs, commits, and tags from the local filesystem.
2.  **Processing (`chunker.py`):** Slices text mathematically to ensure the LLM receives optimal context without hallucinating.
3.  **Generation (`llm.py` & `prompts.py`):** Assembles the payload and securely interfaces with the LLM provider.
4.  **Presentation (`output.py`):** Formats the AI response into Markdown or raw text.

---

## 🤝 Contributing

Contributions are always welcome! Whether it's adding support for a new LLM provider, improving the chunking algorithm, or fixing a typo.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

Please ensure you run the test suite in the `tests/` directory before opening a PR!

---

## ⭐️ Support the Project

If you find ReleaseWave helpful in automating your workflow, please consider **giving the repository a star ⭐️**! It helps the project gain visibility and supports the long-term goal of bringing this tool to more open-source maintainers.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
```
