"""
Configuration management for ReleaseWave.

Supports zero-config mode + optional .rwave.yml for persistent settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


# ── Default Configuration ─────────────────────────────────────────────────────

DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_TOKEN_BUDGET = 120_000  # Max tokens per LLM call
DEFAULT_CHUNK_SIZE = 80_000     # Max tokens per diff chunk
DEFAULT_MAX_RETRIES = 3
DEFAULT_OUTPUT_DIR = "."

CONFIG_FILENAMES = [".rwave.yml", ".rwave.yaml", ".releasewave.yml", ".releasewave.yaml"]


class LLMConfig(BaseModel):
    """LLM-specific configuration."""

    model: str = Field(default=DEFAULT_MODEL, description="LLM model identifier for LiteLLM")
    api_key: Optional[str] = Field(default=None, description="API key (overrides env var)")
    api_base: Optional[str] = Field(default=None, description="Custom API base URL")
    temperature: float = Field(default=0.3, description="Generation temperature")
    max_retries: int = Field(default=DEFAULT_MAX_RETRIES, description="Max retries on failure")
    token_budget: int = Field(default=DEFAULT_TOKEN_BUDGET, description="Max context tokens")
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, description="Max tokens per diff chunk")
    timeout: int = Field(default=120, description="Request timeout in seconds")


class OutputConfig(BaseModel):
    """Output configuration."""

    directory: str = Field(default=DEFAULT_OUTPUT_DIR, description="Output directory for files")
    audiences: list[str] = Field(
        default_factory=lambda: ["developer", "user", "tweet"],
        description="Audience types to generate",
    )
    format: str = Field(default="markdown", description="Output format: markdown, json, text")
    update_changelog: bool = Field(
        default=False,
        description="Whether to prepend to existing CHANGELOG.md",
    )
    changelog_file: str = Field(default="CHANGELOG.md", description="Changelog file to update")
    stdout: bool = Field(default=True, description="Also print output to stdout")


class MonorepoConfig(BaseModel):
    """Monorepo configuration."""

    enabled: bool = Field(default=True, description="Auto-detect monorepo structure")
    packages_dirs: list[str] = Field(
        default_factory=lambda: ["packages", "apps", "libs", "modules", "crates", "services"],
        description="Directories to scan for packages",
    )
    package_markers: list[str] = Field(
        default_factory=lambda: [
            "package.json",
            "pyproject.toml",
            "setup.py",
            "Cargo.toml",
            "go.mod",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
        ],
        description="File markers that indicate a package root",
    )


class FilterConfig(BaseModel):
    """Diff filtering configuration."""

    exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            "*.lock",
            "*.min.js",
            "*.min.css",
            "*.map",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "Cargo.lock",
            "go.sum",
            "*.pb.go",
            "*.generated.*",
            "dist/*",
            "build/*",
            "node_modules/*",
            ".next/*",
            "__pycache__/*",
            "*.pyc",
        ],
        description="Glob patterns to exclude from diff analysis",
    )
    max_file_size: int = Field(
        default=50_000,
        description="Max chars per file diff (larger files get truncated)",
    )
    include_binary_notice: bool = Field(
        default=True,
        description="Note binary file changes in output",
    )


class ReleaseWaveConfig(BaseModel):
    """Root configuration for ReleaseWave."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    monorepo: MonorepoConfig = Field(default_factory=MonorepoConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    custom_prompt: Optional[str] = Field(
        default=None,
        description="Custom instruction to append to the analysis prompt",
    )
    project_context: Optional[str] = Field(
        default=None,
        description="Brief description of the project for better LLM understanding",
    )


# ── Configuration Loading ────────────────────────────────────────────────────

def find_config_file(repo_path: Path) -> Optional[Path]:
    """Search for a .rwave.yml config file in the repo root."""
    for name in CONFIG_FILENAMES:
        config_path = repo_path / name
        if config_path.exists():
            return config_path
    return None


def load_config(
    repo_path: Path,
    cli_overrides: Optional[dict[str, Any]] = None,
) -> ReleaseWaveConfig:
    """
    Load configuration with precedence:
    1. CLI flags (highest)
    2. Environment variables
    3. Config file (.rwave.yml)
    4. Defaults (lowest)
    """
    config_data: dict[str, Any] = {}

    # Load from config file if it exists
    config_file = find_config_file(repo_path)
    if config_file:
        with open(config_file) as f:
            file_data = yaml.safe_load(f)
            if file_data and isinstance(file_data, dict):
                config_data = file_data

    # Build config from file data
    config = ReleaseWaveConfig(**config_data) if config_data else ReleaseWaveConfig()

    # Apply environment variable overrides
    env_model = os.environ.get("RWAVE_MODEL") or os.environ.get("RELEASEWAVE_MODEL")
    if env_model:
        config.llm.model = env_model

    env_api_key = os.environ.get("RWAVE_API_KEY") or os.environ.get("RELEASEWAVE_API_KEY")
    if env_api_key:
        config.llm.api_key = env_api_key

    env_api_base = os.environ.get("RWAVE_API_BASE") or os.environ.get("RELEASEWAVE_API_BASE")
    if env_api_base:
        config.llm.api_base = env_api_base

    # Apply CLI overrides
    if cli_overrides:
        if "model" in cli_overrides and cli_overrides["model"]:
            config.llm.model = cli_overrides["model"]
        if "output_dir" in cli_overrides and cli_overrides["output_dir"]:
            config.output.directory = cli_overrides["output_dir"]
        if "audiences" in cli_overrides and cli_overrides["audiences"]:
            config.output.audiences = cli_overrides["audiences"]
        if "format" in cli_overrides and cli_overrides["format"]:
            config.output.format = cli_overrides["format"]
        if "update_changelog" in cli_overrides:
            config.output.update_changelog = cli_overrides["update_changelog"]
        if "no_stdout" in cli_overrides:
            config.output.stdout = not cli_overrides["no_stdout"]

    return config


def generate_example_config() -> str:
    """Generate an example .rwave.yml config file."""
    return """# ReleaseWave Configuration
# Place this file as .rwave.yml in your repository root.

# LLM Settings
llm:
  # Model identifier (LiteLLM format)
  # Examples: gemini/gemini-2.5-flash, gpt-4o-mini, claude-sonnet-4-20250514, ollama/llama3
  model: gemini/gemini-2.5-flash

  # Temperature for generation (0.0 = deterministic, 1.0 = creative)
  temperature: 0.3

  # Max retries on API failure
  max_retries: 3

  # Token budget per LLM call
  token_budget: 120000

  # Timeout in seconds
  timeout: 120

# Output Settings
output:
  # Directory for generated changelog files
  directory: "."

  # Audience types to generate
  audiences:
    - developer   # Technical changelog with file paths and code details
    - user        # User-facing release notes in plain English
    - tweet       # Tweet-sized announcement (~280 chars)

  # Output format: markdown, json, text
  format: markdown

  # Prepend to existing CHANGELOG.md
  update_changelog: false

  # Print to stdout
  stdout: true

# Monorepo Detection
monorepo:
  enabled: true
  packages_dirs:
    - packages
    - apps
    - libs
    - modules
    - services

# Diff Filters
filters:
  exclude_patterns:
    - "*.lock"
    - "*.min.js"
    - "*.min.css"
    - "package-lock.json"
    - "yarn.lock"
    - "pnpm-lock.yaml"
    - "node_modules/*"
    - "dist/*"
    - "build/*"
    - "__pycache__/*"

  # Max characters per file diff
  max_file_size: 50000

# Optional: Brief project description for better analysis
# project_context: "A React web app with a Python backend API"

# Optional: Custom instruction appended to the analysis prompt
# custom_prompt: "Focus especially on API changes and database migrations"
"""
