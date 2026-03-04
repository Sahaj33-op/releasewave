"""
LLM integration layer for ReleaseWave.

Uses LiteLLM for provider-agnostic model access with
streaming, retry logic, and structured output parsing.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from litellm import completion
from rich.console import Console
from rich.status import Status

from releasewave.chunker import (
    chunk_diffs,
    format_chunk_for_llm,
    format_commits_for_llm,
)
from releasewave.config import ReleaseWaveConfig
from releasewave.models import (
    AnalysisResult,
    AudienceType,
    ChangeEntry,
    ChangelogOutput,
    CommitInfo,
    FileDiff,
)
from releasewave.prompts import (
    build_analysis_prompt,
    build_developer_changelog_prompt,
    build_fallback_prompt,
    build_merge_prompt,
    build_tweet_prompt,
    build_user_changelog_prompt,
)

console = Console(stderr=True)


# ── Core LLM Call ────────────────────────────────────────────────────────────

def call_llm(
    messages: list[dict[str, str]],
    config: ReleaseWaveConfig,
    json_mode: bool = False,
    description: str = "Processing",
    response_model: Optional[type] = None,
) -> Any:
    """
    Make a single LLM call with retry logic and error handling.

    Args:
        messages: Chat messages in OpenAI format
        config: ReleaseWave configuration
        json_mode: Whether to request JSON response format
        description: Human-readable description for status display
        response_model: Optional Pydantic model for structured output via instructor

    Returns:
        The LLM response text or parsed Pydantic model
    """
    kwargs: dict[str, Any] = {
        "model": config.llm.model,
        "messages": messages,
        "temperature": config.llm.temperature,
        "timeout": config.llm.timeout,
    }

    # Set API key if provided
    if config.llm.api_key:
        kwargs["api_key"] = config.llm.api_key
    if config.llm.api_base:
        kwargs["api_base"] = config.llm.api_base

    # Request JSON format if supported (and not using instructor)
    if json_mode and not response_model:
        kwargs["response_format"] = {"type": "json_object"}

    last_error: Optional[Exception] = None

    for attempt in range(1, config.llm.max_retries + 1):
        try:
            if response_model:
                import instructor
                from litellm import completion as litellm_completion
                # Use Instructor to guarantee structured Pydantic output
                client = instructor.from_litellm(litellm_completion)
                return client.chat.completions.create(
                    response_model=response_model,
                    **kwargs
                )
            else:
                response = completion(**kwargs)
                content = response.choices[0].message.content
                if content:
                    return content.strip()
                raise ValueError("Empty response from LLM")

        except Exception as e:
            last_error = e
            if attempt < config.llm.max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                console.print(
                    f"  [yellow]⚠ Attempt {attempt}/{config.llm.max_retries} failed: {e}[/yellow]"
                )
                console.print(f"  [dim]Retrying in {wait_time}s...[/dim]")
                time.sleep(wait_time)
            else:
                console.print(
                    f"  [red]✗ All {config.llm.max_retries} attempts failed[/red]"
                )

    raise RuntimeError(
        f"LLM call failed after {config.llm.max_retries} attempts: {last_error}"
    )


# ── JSON Parsing ─────────────────────────────────────────────────────────────

def parse_analysis_json(raw: str) -> AnalysisResult:
    """
    Parse LLM response into AnalysisResult, handling common JSON issues.
    """
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        console.print(f"  [yellow]⚠ JSON parse error: {e}[/yellow]")
        console.print(f"  [dim]Attempting to extract JSON from response...[/dim]")

        # Try to find JSON object in the response
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                # Return empty analysis
                return AnalysisResult(
                    summary="Failed to parse LLM analysis output.",
                    highlights=["Analysis produced but could not be parsed."],
                )
        else:
            return AnalysisResult(
                summary="Failed to parse LLM analysis output.",
                highlights=["Analysis produced but could not be parsed."],
            )

    # Build AnalysisResult from parsed data
    changes = []
    for entry in data.get("changes", []):
        try:
            changes.append(ChangeEntry(**entry))
        except Exception:
            # Skip malformed entries
            continue

    return AnalysisResult(
        changes=changes,
        summary=data.get("summary", ""),
        highlights=data.get("highlights", []),
    )


# ── Analysis Pipeline ────────────────────────────────────────────────────────

def analyze_changes(
    commits: list[CommitInfo],
    diffs: list[FileDiff],
    config: ReleaseWaveConfig,
) -> AnalysisResult:
    """
    Run the full LLM analysis pipeline on commits and diffs.

    For large diffs, chunks them and merges results.
    Falls back to commit-only mode if diff analysis fails.
    """
    commit_log = format_commits_for_llm(commits)

    # Chunk diffs by token budget
    chunks = chunk_diffs(diffs, max_chunk_tokens=config.llm.chunk_size)

    console.print(
        f"  [dim]Analyzing {len(diffs)} files in {len(chunks)} chunk(s)...[/dim]"
    )

    if len(chunks) == 0:
        # No diffs, analyze commits only
        console.print("  [yellow]⚠ No diffs found, using commit messages only[/yellow]")
        return _analyze_commits_only(commits, commit_log, config)

    if len(chunks) == 1:
        # Single chunk — straightforward analysis
        return _analyze_single_chunk(chunks[0], commit_log, config)

    # Multiple chunks — analyze each, then merge
    return _analyze_multi_chunk(chunks, commit_log, config)


def _analyze_single_chunk(chunk, commit_log: str, config: ReleaseWaveConfig) -> AnalysisResult:
    """Analyze a single chunk of diffs."""
    diff_content = format_chunk_for_llm(chunk)

    messages = build_analysis_prompt(
        diff_content=diff_content,
        commit_log=commit_log,
        project_context=config.project_context,
        custom_prompt=config.custom_prompt,
    )

    with Status("[bold cyan]Analyzing diffs with LLM...", console=console):
        analysis = call_llm(
            messages, config, json_mode=True, 
            description="Analyzing diffs", response_model=AnalysisResult
        )

    return analysis


def _analyze_multi_chunk(chunks, commit_log: str, config: ReleaseWaveConfig) -> AnalysisResult:
    """Analyze multiple chunks and merge results hierarchically to avoid token bottlenecks."""
    chunk_results: list[AnalysisResult] = []

    for i, chunk in enumerate(chunks, 1):
        console.print(f"  [dim]Processing chunk {i}/{len(chunks)}...[/dim]")
        diff_content = format_chunk_for_llm(chunk)

        messages = build_analysis_prompt(
            diff_content=diff_content,
            commit_log=commit_log,  # Full commit log passed to every chunk to provide context
            project_context=config.project_context,
            custom_prompt=config.custom_prompt,
        )

        with Status(
            f"[bold cyan]Analyzing chunk {i}/{len(chunks)}...",
            console=console,
        ):
            res = call_llm(
                messages, config, json_mode=True,
                description=f"Analyzing chunk {i}/{len(chunks)}",
                response_model=AnalysisResult
            )
            chunk_results.append(res)

    # Hierarchical Merge: merge chunks in groups of 3
    console.print("  [dim]Merging chunk analyses...[/dim]")
    
    merged_results = chunk_results
    while len(merged_results) > 1:
        next_level = []
        batch_size = 3
        
        for i in range(0, len(merged_results), batch_size):
            batch = merged_results[i:i+batch_size]
            if len(batch) == 1:
                next_level.append(batch[0])
                continue
            
            # Convert batch to JSON strings to pass into merge prompt
            batch_strs = [json.dumps(r.model_dump(), default=str) for r in batch]
            merge_messages = build_merge_prompt(batch_strs)
            
            with Status(f"[bold cyan]Merging {len(batch)} analyses...", console=console):
                merged = call_llm(
                    merge_messages, config, json_mode=True,
                    description="Merging chunk analyses",
                    response_model=AnalysisResult
                )
                next_level.append(merged)
                
        merged_results = next_level

    return merged_results[0]


def _analyze_commits_only(
    commits: list[CommitInfo],
    commit_log: str,
    config: ReleaseWaveConfig,
) -> AnalysisResult:
    """Fallback: analyze using commit messages only (no diffs)."""
    messages = build_fallback_prompt(commit_log, "from", "to")

    with Status("[bold cyan]Analyzing commits...", console=console):
        analysis = call_llm(
            messages, config, json_mode=True, 
            description="Analyzing commits", response_model=AnalysisResult
        )

    return analysis


# ── Audience Rendering ───────────────────────────────────────────────────────

def render_changelogs(
    analysis: AnalysisResult,
    version_from: str,
    version_to: str,
    config: ReleaseWaveConfig,
) -> list[ChangelogOutput]:
    """
    Render the analysis into multiple audience-targeted changelogs.
    """
    analysis_json = json.dumps(analysis.model_dump(), indent=2, default=str)
    changelogs: list[ChangelogOutput] = []

    audience_builders = {
        "developer": (
            build_developer_changelog_prompt,
            "Developer Changelog",
            AudienceType.DEVELOPER,
        ),
        "user": (
            build_user_changelog_prompt,
            "User Release Notes",
            AudienceType.USER,
        ),
        "tweet": (
            build_tweet_prompt,
            "Tweet Announcement",
            AudienceType.TWEET,
        ),
    }

    for audience_key in config.output.audiences:
        if audience_key not in audience_builders:
            console.print(f"  [yellow]⚠ Unknown audience: {audience_key}, skipping[/yellow]")
            continue

        builder, title, audience_type = audience_builders[audience_key]

        messages = builder(analysis_json, version_from, version_to)

        with Status(
            f"[bold cyan]Generating {title}...",
            console=console,
        ):
            content = call_llm(
                messages, config, json_mode=False,
                description=f"Rendering {title}",
            )

        changelogs.append(ChangelogOutput(
            audience=audience_type,
            content=content,
            title=title,
        ))

    return changelogs
