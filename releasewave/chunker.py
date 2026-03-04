"""
Diff chunking for token-safe LLM analysis.

Splits large diffs into chunks that fit within token budgets,
grouping related files together when possible.
"""

from __future__ import annotations

from releasewave.models import DiffChunk, FileDiff


# ── Token Estimation ──────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a string.

    Uses tiktoken if available, with a simple heuristic (~4 chars per token)
    as a fallback.
    """
    if not text:
        return 0
        
    try:
        import tiktoken
        # Use standard generic encoding
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text, disallowed_special=()))
    except Exception:
        return max(1, len(text) // 4)


def estimate_file_tokens(file_diff: FileDiff) -> int:
    """Estimate tokens needed for a file diff including metadata."""
    metadata_overhead = estimate_tokens(
        f"File: {file_diff.path}\nChange type: {file_diff.change_type}\n"
        f"Additions: {file_diff.additions} Deletions: {file_diff.deletions}\n"
    )
    content_tokens = estimate_tokens(file_diff.diff_content)
    return metadata_overhead + content_tokens


# ── Chunking Strategies ──────────────────────────────────────────────────────

def chunk_diffs(
    diffs: list[FileDiff],
    max_chunk_tokens: int = 80_000,
) -> list[DiffChunk]:
    """
    Split file diffs into token-safe chunks for LLM analysis.

    Strategy:
    1. Group files by directory when possible (related changes stay together)
    2. Never exceed max_chunk_tokens per chunk
    3. Large single files get their own chunk (may still exceed budget — the
       file-level truncation in git_ops handles that)
    """
    if not diffs:
        return []

    # Sort files by directory to group related changes
    sorted_diffs = sorted(diffs, key=_file_sort_key)

    chunks: list[DiffChunk] = []
    current_files: list[FileDiff] = []
    current_tokens = 0
    chunk_id = 1

    for file_diff in sorted_diffs:
        file_tokens = estimate_file_tokens(file_diff)

        # If adding this file would exceed budget, finalize current chunk
        if current_files and (current_tokens + file_tokens) > max_chunk_tokens:
            chunks.append(DiffChunk(
                chunk_id=chunk_id,
                files=current_files,
                estimated_tokens=current_tokens,
            ))
            chunk_id += 1
            current_files = []
            current_tokens = 0

        current_files.append(file_diff)
        current_tokens += file_tokens

    # Don't forget the last chunk
    if current_files:
        chunks.append(DiffChunk(
            chunk_id=chunk_id,
            files=current_files,
            estimated_tokens=current_tokens,
        ))

    return chunks


def _file_sort_key(diff: FileDiff) -> tuple[str, str]:
    """Sort key that groups files by directory."""
    parts = diff.path.rsplit("/", 1)
    if len(parts) == 2:
        return (parts[0], parts[1])
    return ("", parts[0])


# ── Chunk Formatting ─────────────────────────────────────────────────────────

def format_chunk_for_llm(chunk: DiffChunk) -> str:
    """
    Format a diff chunk into a string suitable for LLM analysis.
    Includes file metadata and diff content in a structured format.
    """
    parts: list[str] = []

    parts.append(f"=== Diff Chunk {chunk.chunk_id} ({len(chunk.files)} files) ===\n")

    for file_diff in chunk.files:
        parts.append(f"--- File: {file_diff.path} ---")
        parts.append(f"Change type: {_describe_change_type(file_diff.change_type)}")

        if file_diff.old_path:
            parts.append(f"Renamed from: {file_diff.old_path}")

        if file_diff.is_binary:
            parts.append("[Binary file — content not shown]")
        else:
            parts.append(f"Lines: +{file_diff.additions} / -{file_diff.deletions}")
            if file_diff.diff_content:
                parts.append("")
                parts.append(file_diff.diff_content)

        parts.append("")  # Blank line between files

    return "\n".join(parts)


def format_commits_for_llm(commits: list) -> str:
    """Format commits into a structured string for LLM analysis."""
    if not commits:
        return "No commits in range."

    parts: list[str] = []
    parts.append(f"=== {len(commits)} Commits ===\n")

    for commit in commits:
        parts.append(f"[{commit.short_sha}] {commit.subject}")
        parts.append(f"  Author: {commit.author_name} <{commit.author_email}>")
        parts.append(f"  Date:   {commit.timestamp}")

        # Include full message if it differs from subject (multi-line messages)
        if commit.message != commit.subject and len(commit.message) > len(commit.subject):
            body = commit.message[len(commit.subject):].strip()
            if body:
                parts.append(f"  Body:   {body[:500]}")

        parts.append("")

    return "\n".join(parts)


def _describe_change_type(ct: str) -> str:
    """Human-readable change type."""
    return {
        "A": "Added (new file)",
        "M": "Modified",
        "D": "Deleted",
        "R": "Renamed",
        "C": "Copied",
        "T": "Type changed",
    }.get(ct, ct)
