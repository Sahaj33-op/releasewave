# Changelog: v1.0.0 → v1.1.0

## ✨ Features
- **Introduce ReleaseWave - AI-powered changelog generator**
  - Initial release of the core engine that analyzes actual code diffs, not just commit messages, to generate audience-targeted changelogs (developer, user, tweet).
  - Implemented in `releasewave/cli.py`, `releasewave/git_ops.py`, `releasewave/llm.py`, and related modules.
  - (Commits: 06729ac, f4750f2, 37f6c5f, 6e07e01, 5798962, 3925801)

- **GitHub Action integration**
  - Added a new GitHub Action (`action.yml`) for automated changelog generation in CI/CD pipelines.
  - Includes an example workflow in `.github/workflows/release-notes.yml` for generating release notes on tag publication.
  - (Commits: 06729ac, f4750f2, 37f6c5f, 6e07e01, 5798962, 3925801)

## 🔧 Internal / Refactoring
- **Comprehensive documentation and examples**
  - Added a Product Requirements Document (`prd.md`) and an example configuration file (`.rwave.yml.example`) to guide users and contributors.
  - (Commits: 06729ac, f4750f2, 37f6c5f, 6e07e01, 5798962, 3925801)

- **Test suite implementation**
  - Established a comprehensive test suite covering core functionality like chunking, configuration, models, and prompts.
  - Tests are located in the `tests/` directory, including `test_chunker.py`, `test_config.py`, etc.
  - (Commits: 06729ac, f4750f2, 37f6c5f, 6e07e01, 5798962, 3925801)