"""Tests for the config module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from releasewave.config import (
    DEFAULT_MODEL,
    ReleaseWaveConfig,
    find_config_file,
    load_config,
)


class TestDefaultConfig:
    """Test that default configuration is sensible."""

    def test_default_model(self):
        config = ReleaseWaveConfig()
        assert config.llm.model == DEFAULT_MODEL

    def test_default_audiences(self):
        config = ReleaseWaveConfig()
        assert "developer" in config.output.audiences
        assert "user" in config.output.audiences
        assert "tweet" in config.output.audiences

    def test_default_filter_patterns(self):
        config = ReleaseWaveConfig()
        assert "*.lock" in config.filters.exclude_patterns
        assert "package-lock.json" in config.filters.exclude_patterns

    def test_default_monorepo_enabled(self):
        config = ReleaseWaveConfig()
        assert config.monorepo.enabled is True


class TestConfigLoading:
    """Test configuration file loading."""

    def test_find_config_file_none(self, tmp_path):
        assert find_config_file(tmp_path) is None

    def test_find_config_file_rwave_yml(self, tmp_path):
        config_file = tmp_path / ".rwave.yml"
        config_file.write_text("llm:\n  model: gpt-4o\n")
        result = find_config_file(tmp_path)
        assert result == config_file

    def test_find_config_file_releasewave_yml(self, tmp_path):
        config_file = tmp_path / ".releasewave.yml"
        config_file.write_text("llm:\n  model: gpt-4o\n")
        result = find_config_file(tmp_path)
        assert result == config_file

    def test_load_config_from_file(self, tmp_path):
        config_file = tmp_path / ".rwave.yml"
        config_file.write_text(
            "llm:\n  model: gpt-4o\n  temperature: 0.7\n"
        )
        config = load_config(tmp_path)
        assert config.llm.model == "gpt-4o"
        assert config.llm.temperature == 0.7

    def test_load_config_defaults_without_file(self, tmp_path):
        config = load_config(tmp_path)
        assert config.llm.model == DEFAULT_MODEL

    def test_cli_overrides(self, tmp_path):
        config = load_config(tmp_path, cli_overrides={"model": "claude-sonnet-4-20250514"})
        assert config.llm.model == "claude-sonnet-4-20250514"

    def test_env_var_override(self, tmp_path):
        with patch.dict("os.environ", {"RWAVE_MODEL": "gpt-4o-mini"}):
            config = load_config(tmp_path)
            assert config.llm.model == "gpt-4o-mini"

    def test_cli_overrides_env_var(self, tmp_path):
        with patch.dict("os.environ", {"RWAVE_MODEL": "gpt-4o-mini"}):
            config = load_config(tmp_path, cli_overrides={"model": "gpt-4o"})
            assert config.llm.model == "gpt-4o"


class TestFilterConfig:
    """Test filter configuration."""

    def test_default_max_file_size(self):
        config = ReleaseWaveConfig()
        assert config.filters.max_file_size == 50_000

    def test_default_include_binary_notice(self):
        config = ReleaseWaveConfig()
        assert config.filters.include_binary_notice is True
