"""
LLM prompt templates for ReleaseWave.

All prompts are carefully engineered to produce structured,
high-quality changelog output from messy real-world diffs.
"""

from __future__ import annotations

from typing import Optional


# ── Analysis Prompt ──────────────────────────────────────────────────────────

def build_analysis_prompt(
    diff_content: str,
    commit_log: str,
    project_context: Optional[str] = None,
    custom_prompt: Optional[str] = None,
) -> list[dict[str, str]]:
    """
    Build the prompt for analyzing diffs and commits.

    Returns a list of messages in OpenAI chat format.
    """
    system = """You are ReleaseWave, an expert code analyst that generates changelogs by reading actual code diffs.

Your job is to analyze the provided git diffs and commit messages to identify ALL meaningful changes, then categorize and describe them clearly.

IMPORTANT RULES:
1. Read the ACTUAL DIFFS, not just commit messages. Commit messages often lie or are vague.
2. A commit saying "minor fix" might contain a breaking API change — detect that from the diff.
3. Group related commits/changes together into single entries when they form one logical change.
4. Ignore trivial formatting-only changes unless they affect readability significantly.
5. Identify breaking changes by looking for removed/renamed public APIs, changed function signatures, deleted exports, etc.
6. Detect security fixes by looking for input validation, auth changes, dependency updates of known vulnerable packages.

CATEGORIES (use exactly these):
- feature: New functionality added
- fix: Bug fixes
- breaking: Changes that break backward compatibility
- performance: Speed, memory, or efficiency improvements
- security: Security patches or hardening
- deprecation: Features marked as deprecated
- refactor: Code restructuring without functional change
- documentation: Docs, comments, README changes
- internal: CI/CD, tooling, dev-only changes
- dependency: Dependency additions, removals, or updates
- style: Code style, formatting changes
- test: Test additions or modifications

IMPACT LEVELS:
- critical: Affects all users, potential data loss or security issue
- high: Major new feature or significant behavior change
- medium: Notable improvement or fix
- low: Minor change, unlikely to affect most users"""

    user_parts = []

    if project_context:
        user_parts.append(f"PROJECT CONTEXT:\n{project_context}\n")

    user_parts.append(f"COMMIT LOG:\n{commit_log}\n")
    user_parts.append(f"CODE DIFFS:\n{diff_content}\n")

    user_parts.append("""Analyze the above diffs and commits. Respond with VALID JSON only, using this exact schema:
{
  "changes": [
    {
      "category": "<category>",
      "impact": "<impact_level>",
      "title": "<short one-line title>",
      "description": "<detailed description of what changed and why it matters>",
      "files": ["<affected file paths>"],
      "commits": ["<related short SHAs>"],
      "breaking_detail": "<if breaking, migration instructions; otherwise null>"
    }
  ],
  "summary": "<one paragraph summarizing all changes in this release>",
  "highlights": ["<top 3-5 most important changes as bullet points>"]
}

Be thorough but concise. Combine related micro-changes into single entries. Focus on what matters to users and developers.""")

    if custom_prompt:
        user_parts.append(f"\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


# ── Merge Prompt ─────────────────────────────────────────────────────────────

def build_merge_prompt(chunk_results: list[str]) -> list[dict[str, str]]:
    """
    Build a prompt to merge multiple chunk analysis results into one.
    Used when diffs are too large for a single LLM call.
    """
    system = """You are ReleaseWave. You've been given multiple partial analysis results from different chunks of the same release diff.

Your job is to MERGE them into a single cohesive analysis result:
1. Deduplicate changes that appear in multiple chunks
2. Combine related entries that were split across chunks
3. Re-rank by importance
4. Produce one unified summary and highlights list"""

    user_parts = []
    for i, result in enumerate(chunk_results, 1):
        user_parts.append(f"=== CHUNK {i} ANALYSIS ===\n{result}\n")

    user_parts.append("""Merge the above analyses into a single JSON result with the same schema:
{
  "changes": [...],
  "summary": "<unified summary>",
  "highlights": ["<top 3-5 highlights across all chunks>"]
}

Deduplicate, combine related changes, and rank by importance. Return VALID JSON only.""")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


# ── Audience Rendering Prompts ───────────────────────────────────────────────

def build_developer_changelog_prompt(
    analysis_json: str,
    version_from: str,
    version_to: str,
) -> list[dict[str, str]]:
    """Build prompt for developer-facing technical changelog."""

    system = """You are ReleaseWave. Generate a DEVELOPER-facing changelog in Markdown.

This audience wants:
- Technical precision: file paths, function names, API changes
- Breaking changes prominently called out with migration steps
- Grouped by category (Features, Bug Fixes, Breaking Changes, etc.)
- Commit references where relevant
- Code snippets for migration if applicable

Format as clean Markdown with proper headings, bullet points, and code blocks."""

    user = f"""Analysis data:
{analysis_json}

Generate a developer changelog for the release from {version_from} → {version_to}.

Use this structure:
# Changelog: {version_from} → {version_to}

## 🚨 Breaking Changes (only if any exist)
## ✨ Features
## 🐛 Bug Fixes
## ⚡ Performance
## 🔒 Security
## 📦 Dependencies
## 🔧 Internal / Refactoring

Only include sections that have entries. Use emoji prefixes for visual scanning.
Each entry should have a bullet point with the title and a brief technical description.
Reference file paths and commit SHAs where helpful."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_user_changelog_prompt(
    analysis_json: str,
    version_from: str,
    version_to: str,
) -> list[dict[str, str]]:
    """Build prompt for user-facing release notes."""

    system = """You are ReleaseWave. Generate USER-facing release notes in Markdown.

This audience wants:
- Plain English, no jargon
- Impact-focused: what changed FOR THEM, not what code was changed
- Friendly, professional tone
- Breaking changes explained as "what you need to do" not "what we changed"
- No file paths, no commit SHAs, no function names
- Emojis for visual friendliness

Write like you're explaining to a smart non-technical product manager."""

    user = f"""Analysis data:
{analysis_json}

Generate user-facing release notes for {version_from} → {version_to}.

Use this structure:
# What's New in {version_to}

## 🎯 Highlights
(top 3-5 most impactful changes in 1-2 sentences each)

## ⚠️ Important Changes (only if breaking changes exist)
(explain what users need to do, in plain language)

## ✨ New Features
## 🐛 Fixed
## ⚡ Improvements

Keep it scannable. Use short paragraphs. Be enthusiastic but not over-the-top."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_tweet_prompt(
    analysis_json: str,
    version_from: str,
    version_to: str,
) -> list[dict[str, str]]:
    """Build prompt for tweet-sized announcement."""

    system = """You are ReleaseWave. Generate a tweet-sized release announcement.

Requirements:
- Maximum 280 characters total
- Highlight 1-3 key changes
- Use relevant emojis
- Include a call-to-action feel
- Professional but exciting tone
- No hashtags (the user will add their own)

Just output the tweet text, nothing else."""

    user = f"""Analysis data:
{analysis_json}

Generate a single tweet announcing the release from {version_from} → {version_to}.
Maximum 280 characters. Be punchy and highlight what matters most."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ── Fallback Prompt (commit-only mode) ──────────────────────────────────────

def build_fallback_prompt(
    commit_log: str,
    version_from: str,
    version_to: str,
) -> list[dict[str, str]]:
    """
    Build a fallback prompt that uses only commit messages (no diffs).
    Used when LLM analysis of diffs fails.
    """

    system = """You are ReleaseWave. The diff analysis failed, so you're working with commit messages only.
Do your best to generate a useful changelog, but note that you're working without actual code diffs.
Be more conservative in your categorization since you can't verify against the actual changes."""

    user = f"""Commits from {version_from} → {version_to}:
{commit_log}

Analyze these commit messages and generate a JSON analysis:
{{
  "changes": [
    {{
      "category": "<category>",
      "impact": "<impact_level>",
      "title": "<short title>",
      "description": "<description based on commit message>",
      "files": [],
      "commits": ["<short SHAs>"],
      "breaking_detail": null
    }}
  ],
  "summary": "<overall summary>",
  "highlights": ["<top highlights>"]
}}

Group related commits. Interpret vague messages like 'fix', 'wip', 'update' as best you can.
Return VALID JSON only."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
