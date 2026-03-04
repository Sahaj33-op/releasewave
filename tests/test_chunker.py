"""Tests for the chunker module."""

import pytest

from releasewave.chunker import (
    chunk_diffs,
    estimate_tokens,
    estimate_file_tokens,
    format_chunk_for_llm,
    format_commits_for_llm,
)
from releasewave.models import CommitInfo, FileDiff


class TestTokenEstimation:
    """Test token estimation."""

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_string(self):
        tokens = estimate_tokens("hello world")
        assert tokens >= 1

    def test_proportional(self):
        short = estimate_tokens("hello")
        long = estimate_tokens("hello " * 100)
        assert long > short

    def test_file_tokens_includes_metadata(self):
        diff = FileDiff(
            path="src/main.py",
            change_type="M",
            diff_content="+ added line\n- removed line",
            additions=1,
            deletions=1,
        )
        file_tokens = estimate_file_tokens(diff)
        content_tokens = estimate_tokens(diff.diff_content)
        assert file_tokens > content_tokens  # Metadata adds overhead


class TestChunking:
    """Test diff chunking."""

    def test_empty_diffs(self):
        chunks = chunk_diffs([])
        assert chunks == []

    def test_single_small_file(self):
        diffs = [
            FileDiff(
                path="README.md",
                change_type="M",
                diff_content="+ new line",
                additions=1,
                deletions=0,
            )
        ]
        chunks = chunk_diffs(diffs, max_chunk_tokens=10_000)
        assert len(chunks) == 1
        assert len(chunks[0].files) == 1

    def test_multiple_files_single_chunk(self):
        diffs = [
            FileDiff(path=f"file{i}.py", change_type="M", diff_content=f"+ line {i}")
            for i in range(5)
        ]
        chunks = chunk_diffs(diffs, max_chunk_tokens=100_000)
        assert len(chunks) == 1
        assert len(chunks[0].files) == 5

    def test_large_files_split_into_chunks(self):
        # Create files with ~10k tokens each
        diffs = [
            FileDiff(
                path=f"file{i}.py",
                change_type="M",
                diff_content="x" * 40_000,  # ~10k tokens
            )
            for i in range(5)
        ]
        chunks = chunk_diffs(diffs, max_chunk_tokens=25_000)
        assert len(chunks) > 1

    def test_chunk_ids_sequential(self):
        diffs = [
            FileDiff(
                path=f"file{i}.py",
                change_type="M",
                diff_content="x" * 40_000,
            )
            for i in range(4)
        ]
        chunks = chunk_diffs(diffs, max_chunk_tokens=25_000)
        for i, chunk in enumerate(chunks, 1):
            assert chunk.chunk_id == i


class TestFormatting:
    """Test chunk and commit formatting."""

    def test_format_chunk(self):
        from releasewave.models import DiffChunk
        chunk = DiffChunk(
            chunk_id=1,
            files=[
                FileDiff(
                    path="src/main.py",
                    change_type="M",
                    diff_content="+ added line",
                    additions=1,
                    deletions=0,
                )
            ],
            estimated_tokens=100,
        )
        result = format_chunk_for_llm(chunk)
        assert "src/main.py" in result
        assert "Modified" in result
        assert "+ added line" in result

    def test_format_binary_file(self):
        from releasewave.models import DiffChunk
        chunk = DiffChunk(
            chunk_id=1,
            files=[
                FileDiff(
                    path="image.png",
                    change_type="A",
                    diff_content="",
                    is_binary=True,
                )
            ],
            estimated_tokens=10,
        )
        result = format_chunk_for_llm(chunk)
        assert "Binary file" in result

    def test_format_commits(self):
        commits = [
            CommitInfo(
                sha="abc123def456",
                short_sha="abc123d",
                message="Add new feature\n\nDetailed description",
                subject="Add new feature",
                author_name="Test User",
                author_email="test@example.com",
                timestamp="2026-01-01T00:00:00Z",
            )
        ]
        result = format_commits_for_llm(commits)
        assert "abc123d" in result
        assert "Add new feature" in result
        assert "Test User" in result
