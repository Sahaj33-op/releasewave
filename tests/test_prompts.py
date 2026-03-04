"""Tests for the prompts module."""

import pytest

from releasewave.prompts import (
    build_analysis_prompt,
    build_developer_changelog_prompt,
    build_fallback_prompt,
    build_merge_prompt,
    build_tweet_prompt,
    build_user_changelog_prompt,
)


class TestAnalysisPrompt:
    """Test analysis prompt building."""

    def test_basic_prompt(self):
        messages = build_analysis_prompt(
            diff_content="+ added line",
            commit_log="abc123 Add feature",
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "added line" in messages[1]["content"]
        assert "abc123" in messages[1]["content"]

    def test_with_project_context(self):
        messages = build_analysis_prompt(
            diff_content="+ line",
            commit_log="commit",
            project_context="A Python web framework",
        )
        assert "Python web framework" in messages[1]["content"]

    def test_with_custom_prompt(self):
        messages = build_analysis_prompt(
            diff_content="+ line",
            commit_log="commit",
            custom_prompt="Focus on API changes",
        )
        assert "Focus on API changes" in messages[1]["content"]

    def test_system_prompt_contains_categories(self):
        messages = build_analysis_prompt(
            diff_content="+ line",
            commit_log="commit",
        )
        system = messages[0]["content"]
        assert "feature" in system
        assert "fix" in system
        assert "breaking" in system


class TestAudiencePrompts:
    """Test audience-specific prompt building."""

    def test_developer_prompt(self):
        messages = build_developer_changelog_prompt(
            analysis_json='{"changes": []}',
            version_from="v1.0",
            version_to="v1.1",
        )
        assert "developer" in messages[0]["content"].lower() or "technical" in messages[0]["content"].lower()
        assert "v1.0" in messages[1]["content"]
        assert "v1.1" in messages[1]["content"]

    def test_user_prompt(self):
        messages = build_user_changelog_prompt(
            analysis_json='{"changes": []}',
            version_from="v1.0",
            version_to="v1.1",
        )
        assert "user" in messages[0]["content"].lower() or "plain english" in messages[0]["content"].lower()

    def test_tweet_prompt(self):
        messages = build_tweet_prompt(
            analysis_json='{"changes": []}',
            version_from="v1.0",
            version_to="v1.1",
        )
        assert "280" in messages[0]["content"] or "tweet" in messages[0]["content"].lower()


class TestMergePrompt:
    """Test merge prompt for multi-chunk analysis."""

    def test_merge_prompt(self):
        messages = build_merge_prompt([
            '{"changes": [{"title": "Feature A"}]}',
            '{"changes": [{"title": "Feature B"}]}',
        ])
        assert "CHUNK 1" in messages[1]["content"]
        assert "CHUNK 2" in messages[1]["content"]
        assert "Feature A" in messages[1]["content"]
        assert "Feature B" in messages[1]["content"]


class TestFallbackPrompt:
    """Test commit-only fallback prompt."""

    def test_fallback_prompt(self):
        messages = build_fallback_prompt(
            commit_log="abc123 Fix bug",
            version_from="v1.0",
            version_to="v1.1",
        )
        assert "commit messages only" in messages[0]["content"].lower() or "diff analysis failed" in messages[0]["content"].lower()
        assert "abc123" in messages[1]["content"]
