"""Tests for the models module."""

import pytest
from pydantic import ValidationError

from releasewave.models import (
    AnalysisResult,
    AudienceType,
    ChangeCategory,
    ChangeEntry,
    ChangeImpact,
    ChangelogOutput,
    CommitInfo,
    DiffChunk,
    FileDiff,
    MonorepoAnalysis,
    PackageInfo,
    ReleaseChangelog,
)


class TestChangeEntry:
    """Test ChangeEntry model."""

    def test_valid_entry(self):
        entry = ChangeEntry(
            category=ChangeCategory.FEATURE,
            impact=ChangeImpact.HIGH,
            title="Add dark mode",
            description="Added a dark mode toggle to the settings page.",
            files=["src/settings.py"],
            commits=["abc123d"],
        )
        assert entry.category == ChangeCategory.FEATURE
        assert entry.breaking_detail is None

    def test_breaking_entry(self):
        entry = ChangeEntry(
            category=ChangeCategory.BREAKING,
            impact=ChangeImpact.CRITICAL,
            title="Remove deprecated API",
            description="Removed v1 API endpoints.",
            breaking_detail="Migrate to v2 API endpoints. See docs.",
        )
        assert entry.breaking_detail is not None

    def test_default_impact(self):
        entry = ChangeEntry(
            category=ChangeCategory.FIX,
            title="Fix typo",
            description="Fixed a typo in the readme.",
        )
        assert entry.impact == ChangeImpact.MEDIUM


class TestAnalysisResult:
    """Test AnalysisResult model."""

    def test_empty_result(self):
        result = AnalysisResult()
        assert result.changes == []
        assert result.summary == ""
        assert result.highlights == []

    def test_with_changes(self):
        result = AnalysisResult(
            changes=[
                ChangeEntry(
                    category=ChangeCategory.FEATURE,
                    title="New feature",
                    description="Added something cool.",
                )
            ],
            summary="One new feature added.",
            highlights=["Added something cool"],
        )
        assert len(result.changes) == 1


class TestFileDiff:
    """Test FileDiff model."""

    def test_binary_file(self):
        diff = FileDiff(
            path="image.png",
            change_type="A",
            is_binary=True,
        )
        assert diff.is_binary is True
        assert diff.diff_content == ""

    def test_renamed_file(self):
        diff = FileDiff(
            path="new_name.py",
            old_path="old_name.py",
            change_type="R",
        )
        assert diff.old_path == "old_name.py"


class TestReleaseChangelog:
    """Test full ReleaseChangelog model."""

    def test_complete_changelog(self):
        changelog = ReleaseChangelog(
            version_from="v1.0.0",
            version_to="v1.1.0",
            generated_at="2026-01-01T00:00:00Z",
            model_used="gpt-4o-mini",
            total_commits=10,
            total_files_changed=5,
            analysis=AnalysisResult(
                summary="A release with improvements",
                highlights=["New feature X"],
            ),
            changelogs=[
                ChangelogOutput(
                    audience=AudienceType.DEVELOPER,
                    content="# Developer Changelog\n...",
                    title="Developer Changelog",
                ),
            ],
        )
        assert changelog.total_commits == 10
        assert len(changelog.changelogs) == 1
