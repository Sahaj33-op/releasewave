"""Tests for git_ops module.

Covers:
- get_commits with native path filtering
- get_commit_files
- _get_file_diff OOM-safe Popen buffering
- _should_exclude pattern matching
- detect_monorepo
- get_diff_stats
- resolve_ref argument injection guard
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from releasewave.config import ReleaseWaveConfig
from releasewave.models import (
    CommitInfo,
    FileDiff,
    MonorepoAnalysis,
    PackageInfo,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    return ReleaseWaveConfig()


# ── resolve_ref ──────────────────────────────────────────────────────────────

class TestResolveRef:
    """Test ref resolution with argument injection guard."""

    def test_rejects_hyphen_prefix(self):
        from releasewave.git_ops import resolve_ref
        with pytest.raises(ValueError, match="cannot start with '-'"):
            resolve_ref(Path("."), "--exec=malicious")

    def test_rejects_flag_injection(self):
        from releasewave.git_ops import resolve_ref
        with pytest.raises(ValueError, match="cannot start with '-'"):
            resolve_ref(Path("."), "-v")


# ── get_commits ──────────────────────────────────────────────────────────────

class TestGetCommits:
    """Test commit extraction with native path filtering."""

    def test_path_filter_appended_to_git_command(self, tmp_path):
        """When path is provided, git log command includes '-- <path>'."""
        from releasewave.git_ops import get_commits

        separator = "---RWAVE_COMMIT_SEP---"
        field_sep = "---RWAVE_FIELD---"
        fake_output = field_sep.join([
            "abc123full",
            "abc123",
            "feat: add X",
            "feat: add X",
            "Dev",
            "dev@t.com",
            "2026-01-01T00:00:00Z",
        ]) + separator

        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("releasewave.git_ops.subprocess.run", return_value=mock_result) as mock_run:
            with patch("releasewave.git_ops._count_files_changed", return_value=1):
                get_commits(tmp_path, "ref_a", "ref_b", path="packages/web")

                # Verify the git command includes path filter
                cmd_args = mock_run.call_args[0][0]
                assert "--" in cmd_args
                assert "packages/web" in cmd_args

    def test_no_path_filter_by_default(self, tmp_path):
        """Without path, git log command does not include '--'."""
        from releasewave.git_ops import get_commits

        mock_result = MagicMock()
        mock_result.stdout = ""

        with patch("releasewave.git_ops.subprocess.run", return_value=mock_result):
            get_commits(tmp_path, "ref_a", "ref_b")

        cmd_args = subprocess.run

    def test_empty_log_returns_empty_list(self, tmp_path):
        """Empty git log output returns empty commits list."""
        from releasewave.git_ops import get_commits

        mock_result = MagicMock()
        mock_result.stdout = ""

        with patch("releasewave.git_ops.subprocess.run", return_value=mock_result):
            commits = get_commits(tmp_path, "ref_a", "ref_b")
            assert commits == []


# ── get_commit_files ─────────────────────────────────────────────────────────

class TestGetCommitFiles:
    """Test file listing for a specific commit."""

    def test_returns_file_list(self, tmp_path):
        from releasewave.git_ops import get_commit_files

        mock_result = MagicMock()
        mock_result.stdout = "src/main.py\nsrc/utils.py\nREADME.md\n"

        with patch("releasewave.git_ops.subprocess.run", return_value=mock_result):
            files = get_commit_files(tmp_path, "abc123")
            assert files == ["src/main.py", "src/utils.py", "README.md"]

    def test_empty_commit_returns_empty(self, tmp_path):
        from releasewave.git_ops import get_commit_files

        mock_result = MagicMock()
        mock_result.stdout = ""

        with patch("releasewave.git_ops.subprocess.run", return_value=mock_result):
            files = get_commit_files(tmp_path, "abc123")
            assert files == []

    def test_subprocess_failure_returns_empty(self, tmp_path):
        from releasewave.git_ops import get_commit_files

        with patch(
            "releasewave.git_ops.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            files = get_commit_files(tmp_path, "abc123")
            assert files == []


# ── _get_file_diff (OOM-safe Popen) ─────────────────────────────────────────

class TestGetFileDiff:
    """Test OOM-safe diff extraction via Popen."""

    def test_reads_up_to_max_size(self, tmp_path):
        """Output is bounded to max_size bytes."""
        from releasewave.git_ops import _get_file_diff

        large_content = b"x" * 5000

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = large_content[:100]  # max_size=100

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout

        with patch("releasewave.git_ops.subprocess.Popen", return_value=mock_proc):
            result = _get_file_diff(tmp_path, "a", "b", "file.py", max_size=100)
            mock_stdout.read.assert_called_once_with(100)
            assert isinstance(result, str)

    def test_handles_popen_failure(self, tmp_path):
        """Returns empty string on Popen error."""
        from releasewave.git_ops import _get_file_diff

        with patch(
            "releasewave.git_ops.subprocess.Popen",
            side_effect=OSError("spawn failed"),
        ):
            result = _get_file_diff(tmp_path, "a", "b", "file.py")
            assert result == ""


# ── _should_exclude ──────────────────────────────────────────────────────────

class TestShouldExclude:
    """Test file exclusion pattern matching."""

    def test_exact_filename_match(self):
        from releasewave.git_ops import _should_exclude
        assert _should_exclude("package-lock.json", ["package-lock.json"]) is True

    def test_glob_extension_match(self):
        from releasewave.git_ops import _should_exclude
        assert _should_exclude("vendor/dep.lock", ["*.lock"]) is True

    def test_path_glob_match(self):
        from releasewave.git_ops import _should_exclude
        assert _should_exclude("dist/bundle.js", ["dist/*"]) is True

    def test_no_match(self):
        from releasewave.git_ops import _should_exclude
        assert _should_exclude("src/main.py", ["*.lock", "dist/*"]) is False

    def test_basename_match(self):
        from releasewave.git_ops import _should_exclude
        assert _should_exclude("deep/nested/package-lock.json", ["package-lock.json"]) is True


# ── get_diff_stats ───────────────────────────────────────────────────────────

class TestDiffStats:
    """Test diff statistics computation."""

    def test_stats_computation(self):
        from releasewave.git_ops import get_diff_stats

        diffs = [
            FileDiff(path="a.py", change_type="A", diff_content="+line", additions=5, deletions=0),
            FileDiff(path="b.py", change_type="M", diff_content="-old\n+new", additions=3, deletions=2),
            FileDiff(path="c.py", change_type="D", diff_content="-removed", additions=0, deletions=10),
            FileDiff(path="d.py", change_type="R", diff_content="", additions=0, deletions=0),
            FileDiff(path="e.png", change_type="A", diff_content="", is_binary=True),
        ]

        stats = get_diff_stats(diffs)
        assert stats["total_files"] == 5
        assert stats["files_added"] == 2  # a.py + e.png
        assert stats["files_modified"] == 1
        assert stats["files_deleted"] == 1
        assert stats["files_renamed"] == 1
        assert stats["total_additions"] == 8
        assert stats["total_deletions"] == 12
        assert stats["binary_files"] == 1

    def test_empty_diffs(self):
        from releasewave.git_ops import get_diff_stats

        stats = get_diff_stats([])
        assert stats["total_files"] == 0
        assert stats["total_additions"] == 0


# ── detect_monorepo ──────────────────────────────────────────────────────────

class TestDetectMonorepo:
    """Test monorepo detection logic."""

    def test_disabled_returns_false(self, tmp_path, config):
        from releasewave.git_ops import detect_monorepo

        config.monorepo.enabled = False
        result = detect_monorepo(tmp_path, config)
        assert result.is_monorepo is False

    def test_single_package_not_monorepo(self, tmp_path, config):
        """A single package does not qualify as monorepo."""
        from releasewave.git_ops import detect_monorepo

        pkg_dir = tmp_path / "packages" / "web"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text('{"name": "@app/web"}')

        result = detect_monorepo(tmp_path, config)
        assert result.is_monorepo is False
        assert len(result.packages) == 1

    def test_multiple_packages_is_monorepo(self, tmp_path, config):
        """Multiple packages detect as monorepo."""
        from releasewave.git_ops import detect_monorepo

        for name in ["web", "api", "shared"]:
            pkg_dir = tmp_path / "packages" / name
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "package.json").write_text(f'{{"name": "@app/{name}"}}')

        result = detect_monorepo(tmp_path, config)
        assert result.is_monorepo is True
        assert len(result.packages) == 3

    def test_detects_python_packages(self, tmp_path, config):
        """Detects pyproject.toml based packages."""
        from releasewave.git_ops import detect_monorepo

        for name in ["core", "cli"]:
            pkg_dir = tmp_path / "packages" / name
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "pyproject.toml").write_text(f'[project]\nname = "{name}"')

        result = detect_monorepo(tmp_path, config)
        assert result.is_monorepo is True
        pkg_names = {p.name for p in result.packages}
        assert "core" in pkg_names
        assert "cli" in pkg_names
