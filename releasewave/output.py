"""
Output handling for ReleaseWave.

Writes changelog files, updates existing CHANGELOG.md,
prints to stdout, and exports JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from releasewave.models import (
    AudienceType,
    ChangelogOutput,
    ReleaseChangelog,
)

console = Console()
stderr_console = Console(stderr=True)


# ── File Names ───────────────────────────────────────────────────────────────

AUDIENCE_FILENAMES = {
    AudienceType.DEVELOPER: "CHANGELOG-developer.md",
    AudienceType.USER: "RELEASE-NOTES.md",
    AudienceType.TWEET: "TWEET.txt",
}


def get_output_filename(audience: AudienceType, version_to: str) -> str:
    """Get the output filename for an audience type."""
    base = AUDIENCE_FILENAMES.get(audience, f"CHANGELOG-{audience.value}.md")
    return base


# ── File Writing ─────────────────────────────────────────────────────────────

def write_changelogs(
    changelog: ReleaseChangelog,
    output_dir: str = ".",
    write_json: bool = False,
) -> list[Path]:
    """
    Write all changelog outputs to files.

    Returns a list of written file paths.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for cl in changelog.changelogs:
        filename = get_output_filename(cl.audience, changelog.version_to)
        file_path = out_path / filename

        file_path.write_text(cl.content, encoding="utf-8")
        written.append(file_path)
        stderr_console.print(f"  [green]✓[/green] Written: [bold]{file_path}[/bold]")

    # Optionally write full JSON export
    if write_json:
        json_path = out_path / "releasewave-output.json"
        json_data = changelog.model_dump(mode="json")
        json_path.write_text(
            json.dumps(json_data, indent=2, default=str),
            encoding="utf-8",
        )
        written.append(json_path)
        stderr_console.print(f"  [green]✓[/green] Written: [bold]{json_path}[/bold]")

    return written


# ── CHANGELOG.md Update ──────────────────────────────────────────────────────

def update_changelog_file(
    developer_changelog: str,
    changelog_file: str = "CHANGELOG.md",
    repo_path: Optional[Path] = None,
) -> Path:
    """
    Prepend the new changelog to an existing CHANGELOG.md.
    Creates the file if it doesn't exist.
    """
    file_path = Path(repo_path or ".") / changelog_file

    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")

        # Try to insert after the main heading
        lines = existing.split("\n")
        insert_after = 0

        for i, line in enumerate(lines):
            if line.startswith("# ") and i == 0:
                insert_after = i + 1
                # Skip any blank lines after the heading
                while insert_after < len(lines) and not lines[insert_after].strip():
                    insert_after += 1
                break

        # Insert the new changelog
        new_content = (
            "\n".join(lines[:insert_after])
            + "\n\n"
            + developer_changelog
            + "\n\n---\n\n"
            + "\n".join(lines[insert_after:])
        )
    else:
        new_content = f"# Changelog\n\n{developer_changelog}\n"

    file_path.write_text(new_content, encoding="utf-8")
    stderr_console.print(
        f"  [green]✓[/green] Updated: [bold]{file_path}[/bold]"
    )
    return file_path


# ── Stdout Printing ──────────────────────────────────────────────────────────

def print_changelogs(changelogs: list[ChangelogOutput]) -> None:
    """Print all changelogs to stdout with rich formatting."""
    for cl in changelogs:
        # Add a styled panel for each audience
        color = {
            AudienceType.DEVELOPER: "cyan",
            AudienceType.USER: "green",
            AudienceType.TWEET: "magenta",
        }.get(cl.audience, "white")

        emoji = {
            AudienceType.DEVELOPER: "🔧",
            AudienceType.USER: "📋",
            AudienceType.TWEET: "🐦",
        }.get(cl.audience, "📄")

        title = f"{emoji} {cl.title}"

        if cl.audience == AudienceType.TWEET:
            # Tweet is short, just print it directly
            panel = Panel(
                Text(cl.content, style="bold"),
                title=title,
                border_style=color,
                padding=(1, 2),
            )
            console.print(panel)
            char_count = len(cl.content)
            status = "🟢" if char_count <= 280 else "🔴"
            console.print(
                f"  {status} [dim]{char_count}/280 characters[/dim]\n",
            )
        else:
            # Render markdown content
            panel = Panel(
                Markdown(cl.content),
                title=title,
                border_style=color,
                padding=(1, 2),
            )
            console.print(panel)
            console.print()


# ── Summary Statistics ───────────────────────────────────────────────────────

def print_summary(changelog: ReleaseChangelog) -> None:
    """Print a summary of the generation."""
    analysis = changelog.analysis

    # Count by category
    categories = {}
    for change in analysis.changes:
        cat = change.category.value
        categories[cat] = categories.get(cat, 0) + 1

    # Build summary table
    parts = [
        f"[bold]Release:[/bold] {changelog.version_from} → {changelog.version_to}",
        f"[bold]Commits:[/bold] {changelog.total_commits}",
        f"[bold]Files changed:[/bold] {changelog.total_files_changed}",
        f"[bold]Changes detected:[/bold] {len(analysis.changes)}",
        f"[bold]Model:[/bold] {changelog.model_used}",
    ]

    if categories:
        cat_str = ", ".join(f"{k}: {v}" for k, v in sorted(categories.items()))
        parts.append(f"[bold]Breakdown:[/bold] {cat_str}")

    # Check for breaking changes
    breaking = [c for c in analysis.changes if c.category.value == "breaking"]
    if breaking:
        parts.append(f"[bold red]⚠ Breaking changes:[/bold red] {len(breaking)}")

    summary_text = "\n".join(parts)

    panel = Panel(
        summary_text,
        title="📊 ReleaseWave Summary",
        border_style="blue",
        padding=(1, 2),
    )
    stderr_console.print(panel)
