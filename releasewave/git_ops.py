"""
Git operations for ReleaseWave.

Handles ref resolution, diff extraction, commit log parsing,
and monorepo package detection.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

# Common kwargs for all subprocess.run calls to handle Windows encoding
_SUBPROCESS_KWARGS = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}

from rich.console import Console

from releasewave.config import ReleaseWaveConfig
from releasewave.models import (
    CommitInfo,
    FileDiff,
    MonorepoAnalysis,
    PackageInfo,
)

console = Console(stderr=True)


# ── Ref Resolution ────────────────────────────────────────────────────────────

def resolve_ref(repo_path: Path, ref: str) -> str:
    """
    Resolve a git ref (tag, branch, SHA) to a full SHA.
    Raises ValueError if the ref cannot be resolved.
    """
    if str(ref).startswith("-"):
        raise ValueError(f"Invalid git ref '{ref}'. Refs cannot start with '-'.")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            **_SUBPROCESS_KWARGS,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        raise ValueError(
            f"Cannot resolve git ref '{ref}'. "
            f"Make sure it's a valid tag, branch, or commit SHA.\n"
            f"  Tip: Use 'git tag' to list tags, or 'git log --oneline -10' for recent commits."
        )


def validate_repo(repo_path: Path) -> Path:
    """Validate that the given path is inside a git repository. Returns the repo root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            **_SUBPROCESS_KWARGS,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        raise ValueError(
            f"'{repo_path}' is not inside a git repository.\n"
            f"  Run this command from within a git repo, or pass --repo /path/to/repo."
        )


def get_ref_display_name(repo_path: Path, sha: str) -> str:
    """Try to find a human-readable name (tag or branch) for a SHA."""
    # Try tags first
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", sha],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            **_SUBPROCESS_KWARGS,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        pass

    # Fall back to short SHA
    return sha[:7]


# ── Commit Log Extraction ────────────────────────────────────────────────────

def get_commits(repo_path: Path, ref_from: str, ref_to: str) -> list[CommitInfo]:
    """
    Extract all commits between two refs.
    Uses git log with a structured format for reliable parsing.
    """
    separator = "---RWAVE_COMMIT_SEP---"
    field_sep = "---RWAVE_FIELD---"

    log_format = field_sep.join([
        "%H",           # Full SHA
        "%h",           # Short SHA
        "%B",           # Full message body
        "%s",           # Subject (first line)
        "%an",          # Author name
        "%ae",          # Author email
        "%aI",          # Author date ISO
    ]) + separator

    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--format={log_format}",
                f"{ref_from}..{ref_to}",
            ],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            **_SUBPROCESS_KWARGS,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to extract git log: {e.stderr}")

    commits: list[CommitInfo] = []
    raw_commits = result.stdout.split(separator)

    for raw in raw_commits:
        raw = raw.strip()
        if not raw:
            continue

        fields = raw.split(field_sep)
        if len(fields) < 7:
            continue

        # Get files changed count for this commit
        files_changed = _count_files_changed(repo_path, fields[0].strip())

        commits.append(CommitInfo(
            sha=fields[0].strip(),
            short_sha=fields[1].strip(),
            message=fields[2].strip(),
            subject=fields[3].strip(),
            author_name=fields[4].strip(),
            author_email=fields[5].strip(),
            timestamp=fields[6].strip(),
            files_changed=files_changed,
        ))

    return commits


def _count_files_changed(repo_path: Path, sha: str) -> int:
    """Count the number of files changed in a commit."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            **_SUBPROCESS_KWARGS,
        )
        return len([f for f in result.stdout.strip().split("\n") if f.strip()])
    except subprocess.CalledProcessError:
        return 0


# ── Diff Extraction ──────────────────────────────────────────────────────────

def get_file_diffs(
    repo_path: Path,
    ref_from: str,
    ref_to: str,
    config: ReleaseWaveConfig,
) -> list[FileDiff]:
    """
    Extract per-file diffs between two refs.
    Applies filters from config (exclusions, size limits).
    """
    # First, get the list of changed files with their change types
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "--diff-filter=ACDMRT", ref_from, ref_to],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            **_SUBPROCESS_KWARGS,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to extract git diff: {e.stderr}")

    file_entries = _parse_name_status(result.stdout)
    diffs: list[FileDiff] = []
    excluded_count = 0

    for change_type, path, old_path in file_entries:
        # Apply exclusion filters
        if _should_exclude(path, config.filters.exclude_patterns):
            excluded_count += 1
            continue

        # Check if binary
        is_binary = _is_binary_file(repo_path, ref_to, path)

        if is_binary:
            diffs.append(FileDiff(
                path=path,
                old_path=old_path,
                change_type=change_type,
                diff_content="[Binary file changed]",
                is_binary=True,
            ))
            continue

        # Get the actual diff content for this file
        diff_content = _get_file_diff(repo_path, ref_from, ref_to, path)
        if diff_content is None:
            diff_content = ""

        # Truncate if too long (line-aware)
        if len(diff_content) > config.filters.max_file_size:
            diff_lines = diff_content.split('\n')
            allowed_lines = []
            current_len = 0
            for line in diff_lines:
                # +1 for newline character
                if current_len + len(line) + 1 > config.filters.max_file_size:
                    break
                allowed_lines.append(line)
                current_len += len(line) + 1
                
            diff_content = (
                "\n".join(allowed_lines)
                + f"\n\n[... truncated at {current_len} chars, "
                f"full diff is {len(diff_content)} chars ...]"
            )

        # Count additions and deletions
        additions, deletions = _count_changes(diff_content)

        diffs.append(FileDiff(
            path=path,
            old_path=old_path,
            change_type=change_type,
            diff_content=diff_content,
            is_binary=False,
            additions=additions,
            deletions=deletions,
        ))

    if excluded_count > 0:
        console.print(
            f"  [dim]Excluded {excluded_count} files matching filter patterns[/dim]"
        )

    return diffs


def _parse_name_status(output: str) -> list[tuple[str, str, Optional[str]]]:
    """Parse git diff --name-status output into (change_type, path, old_path) tuples."""
    entries = []
    for line in output.strip().split("\n"):
        if not line.strip():
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        change_type = parts[0][0]  # First char: A, M, D, R, C, T
        path = parts[-1]           # Current path is always last
        old_path = parts[1] if len(parts) > 2 else None  # Old path for renames

        entries.append((change_type, path, old_path))

    return entries


def _should_exclude(path: str, patterns: list[str]) -> bool:
    """Check if a file path matches any exclusion pattern."""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if fnmatch.fnmatch(os.path.basename(path), pattern):
            return True
    return False


def _is_binary_file(repo_path: Path, ref: str, path: str) -> bool:
    """Check if a file is binary using git's detection."""
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", f"{ref}~1", ref, "--", path],
            cwd=str(repo_path),
            capture_output=True,
            **_SUBPROCESS_KWARGS,
        )
        # Binary files show as "-\t-\t<path>" in numstat
        if result.stdout.strip().startswith("-\t-"):
            return True
    except subprocess.CalledProcessError:
        pass

    # Fallback: check common binary extensions
    binary_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".woff", ".woff2", ".ttf", ".eot", ".otf",
        ".pdf", ".zip", ".gz", ".tar", ".bz2",
        ".exe", ".dll", ".so", ".dylib",
        ".mp3", ".mp4", ".wav", ".avi", ".mov",
        ".db", ".sqlite", ".sqlite3",
    }
    return Path(path).suffix.lower() in binary_extensions


def _get_file_diff(repo_path: Path, ref_from: str, ref_to: str, path: str) -> str:
    """Get the unified diff for a single file."""
    try:
        result = subprocess.run(
            ["git", "diff", ref_from, ref_to, "--", path],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            **_SUBPROCESS_KWARGS,
        )
        return result.stdout or ""
    except (subprocess.CalledProcessError, UnicodeDecodeError):
        return ""


def _count_changes(diff_content: str) -> tuple[int, int]:
    """Count additions and deletions in a unified diff."""
    additions = 0
    deletions = 0
    for line in diff_content.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


# ── Monorepo Detection ───────────────────────────────────────────────────────

def detect_monorepo(repo_path: Path, config: ReleaseWaveConfig) -> MonorepoAnalysis:
    """
    Detect if the repository is a monorepo and identify packages.
    Looks for common monorepo patterns and package markers.
    """
    if not config.monorepo.enabled:
        return MonorepoAnalysis(is_monorepo=False)

    packages: list[PackageInfo] = []

    for packages_dir in config.monorepo.packages_dirs:
        pkg_path = repo_path / packages_dir
        if not pkg_path.is_dir():
            continue

        # Scan for package markers in subdirectories
        for subdir in pkg_path.iterdir():
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue

            for marker in config.monorepo.package_markers:
                marker_path = subdir / marker
                if marker_path.exists():
                    pkg_name = _extract_package_name(marker_path, subdir.name)
                    packages.append(PackageInfo(
                        name=pkg_name,
                        path=str(subdir.relative_to(repo_path)),
                        detected_by=marker,
                    ))
                    break  # Found a marker, no need to check others

    # Also check root-level workspace configs
    if not packages:
        # Check for npm/yarn/pnpm workspaces
        root_pkg_json = repo_path / "package.json"
        if root_pkg_json.exists():
            packages.extend(_detect_npm_workspaces(repo_path, root_pkg_json))

        # Check for Python monorepos (poetry workspaces, etc.)
        root_pyproject = repo_path / "pyproject.toml"
        if root_pyproject.exists():
            packages.extend(_detect_python_packages(repo_path))

    return MonorepoAnalysis(
        is_monorepo=len(packages) > 1,
        packages=packages,
    )


def _extract_package_name(marker_path: Path, fallback_name: str) -> str:
    """Extract the package name from the marker file."""
    try:
        if marker_path.name == "package.json":
            import json
            with open(marker_path) as f:
                data = json.load(f)
                return data.get("name", fallback_name)
        elif marker_path.name == "pyproject.toml":
            content = marker_path.read_text()
            match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        elif marker_path.name == "Cargo.toml":
            content = marker_path.read_text()
            match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
    except Exception:
        pass
    return fallback_name


def _detect_npm_workspaces(repo_path: Path, pkg_json_path: Path) -> list[PackageInfo]:
    """Detect npm/yarn/pnpm workspace packages."""
    import json

    packages: list[PackageInfo] = []
    try:
        with open(pkg_json_path) as f:
            data = json.load(f)

        workspaces = data.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])

        for pattern in workspaces:
            # Resolve glob patterns
            import glob as glob_mod
            matched = glob_mod.glob(str(repo_path / pattern), recursive=False)
            for match_path in matched:
                match_path = Path(match_path)
                if match_path.is_dir() and (match_path / "package.json").exists():
                    pkg_name = _extract_package_name(
                        match_path / "package.json",
                        match_path.name,
                    )
                    packages.append(PackageInfo(
                        name=pkg_name,
                        path=str(match_path.relative_to(repo_path)),
                        detected_by="npm-workspace",
                    ))
    except Exception:
        pass

    return packages


def _detect_python_packages(repo_path: Path) -> list[PackageInfo]:
    """Detect Python packages in common directories."""
    packages: list[PackageInfo] = []
    for dirname in ["src", "packages", "libs"]:
        src_dir = repo_path / dirname
        if src_dir.is_dir():
            for subdir in src_dir.iterdir():
                if subdir.is_dir() and (subdir / "pyproject.toml").exists():
                    pkg_name = _extract_package_name(
                        subdir / "pyproject.toml",
                        subdir.name,
                    )
                    packages.append(PackageInfo(
                        name=pkg_name,
                        path=str(subdir.relative_to(repo_path)),
                        detected_by="pyproject.toml",
                    ))
    return packages


# ── Diff Statistics ──────────────────────────────────────────────────────────

def get_diff_stats(diffs: list[FileDiff]) -> dict[str, int]:
    """Compute summary statistics for a list of file diffs."""
    return {
        "total_files": len(diffs),
        "files_added": sum(1 for d in diffs if d.change_type == "A"),
        "files_modified": sum(1 for d in diffs if d.change_type == "M"),
        "files_deleted": sum(1 for d in diffs if d.change_type == "D"),
        "files_renamed": sum(1 for d in diffs if d.change_type == "R"),
        "total_additions": sum(d.additions for d in diffs),
        "total_deletions": sum(d.deletions for d in diffs),
        "binary_files": sum(1 for d in diffs if d.is_binary),
    }
