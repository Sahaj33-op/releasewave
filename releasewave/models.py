"""
Data models for ReleaseWave.

All structured data flowing through the pipeline is typed via Pydantic.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Change Categories ─────────────────────────────────────────────────────────

class ChangeCategory(str, Enum):
    """Semantic categories for changelog entries."""

    FEATURE = "feature"
    FIX = "fix"
    BREAKING = "breaking"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DEPRECATION = "deprecation"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    INTERNAL = "internal"
    DEPENDENCY = "dependency"
    STYLE = "style"
    TEST = "test"


class ChangeImpact(str, Enum):
    """How significant is this change to end users."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Commit & Diff Models ─────────────────────────────────────────────────────

class CommitInfo(BaseModel):
    """A single commit parsed from git log."""

    sha: str = Field(description="Full commit SHA")
    short_sha: str = Field(description="Short 7-char SHA")
    message: str = Field(description="Full commit message")
    subject: str = Field(description="First line of commit message")
    author_name: str = Field(description="Author name")
    author_email: str = Field(description="Author email")
    timestamp: str = Field(description="ISO-format timestamp")
    files_changed: int = Field(default=0, description="Number of files changed")


class FileDiff(BaseModel):
    """Diff for a single file between two refs."""

    path: str = Field(description="File path relative to repo root")
    old_path: Optional[str] = Field(default=None, description="Old path if renamed")
    change_type: str = Field(description="A (added), M (modified), D (deleted), R (renamed)")
    diff_content: str = Field(default="", description="Raw unified diff content")
    is_binary: bool = Field(default=False, description="Whether this is a binary file")
    additions: int = Field(default=0, description="Lines added")
    deletions: int = Field(default=0, description="Lines deleted")


class DiffChunk(BaseModel):
    """A token-safe chunk of diffs for LLM analysis."""

    chunk_id: int = Field(description="Sequential chunk number")
    files: list[FileDiff] = Field(description="Files included in this chunk")
    estimated_tokens: int = Field(default=0, description="Estimated token count")


# ── LLM Analysis Results ─────────────────────────────────────────────────────

class ChangeEntry(BaseModel):
    """A single analyzed change entry produced by the LLM."""

    category: ChangeCategory = Field(description="Category of the change")
    impact: ChangeImpact = Field(default=ChangeImpact.MEDIUM, description="Impact level")
    title: str = Field(description="Short one-line title of the change")
    description: str = Field(description="Detailed description of what changed and why")
    files: list[str] = Field(default_factory=list, description="Affected file paths")
    commits: list[str] = Field(default_factory=list, description="Related commit SHAs")
    breaking_detail: Optional[str] = Field(
        default=None,
        description="If breaking, details about migration/upgrade path",
    )


class AnalysisResult(BaseModel):
    """Complete LLM analysis of a set of changes."""

    changes: list[ChangeEntry] = Field(default_factory=list, description="All detected changes")
    summary: str = Field(default="", description="One-paragraph overall summary")
    highlights: list[str] = Field(
        default_factory=list,
        description="Top 3-5 most important changes as bullet points",
    )


# ── Audience-Targeted Outputs ────────────────────────────────────────────────

class AudienceType(str, Enum):
    """Target audience for the changelog."""

    DEVELOPER = "developer"
    USER = "user"
    TWEET = "tweet"


class ChangelogOutput(BaseModel):
    """A single audience-targeted changelog."""

    audience: AudienceType = Field(description="Target audience")
    content: str = Field(description="Rendered markdown/text content")
    title: str = Field(description="Changelog title/heading")


class ReleaseChangelog(BaseModel):
    """Complete multi-audience changelog for a release."""

    version_from: str = Field(description="Starting ref")
    version_to: str = Field(description="Ending ref")
    generated_at: str = Field(description="ISO timestamp when generated")
    model_used: str = Field(description="LLM model identifier")
    total_commits: int = Field(default=0, description="Number of commits in range")
    total_files_changed: int = Field(default=0, description="Number of files changed")
    analysis: AnalysisResult = Field(description="Full analysis result")
    changelogs: list[ChangelogOutput] = Field(
        default_factory=list,
        description="Per-audience changelog outputs",
    )


# ── Monorepo Models ──────────────────────────────────────────────────────────

class PackageInfo(BaseModel):
    """A detected package/workspace in a monorepo."""

    name: str = Field(description="Package name")
    path: str = Field(description="Relative path from repo root")
    detected_by: str = Field(description="How detected: package.json, pyproject.toml, etc.")


class MonorepoAnalysis(BaseModel):
    """Analysis of a monorepo structure."""

    is_monorepo: bool = Field(default=False, description="Whether this is a monorepo")
    packages: list[PackageInfo] = Field(default_factory=list, description="Detected packages")
    root_changes: list[FileDiff] = Field(
        default_factory=list,
        description="Changes not belonging to any package",
    )
