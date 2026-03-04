"""
ReleaseWave CLI — Full-featured command-line interface.

Usage:
    releasewave <from_ref> <to_ref>           # Zero-config mode
    releasewave v1.0.0 v1.1.0 --model gpt-4o  # Specify model
    releasewave init                            # Generate .rwave.yml

Aliases: `releasewave` or `rwave`
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

# Fix Windows Unicode encoding issues with Rich
# Windows terminals (cp1252) can't render emojis, so we force UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from releasewave import __version__
from releasewave.config import (
    ReleaseWaveConfig,
    generate_example_config,
    load_config,
)
from releasewave.git_ops import (
    get_commits,
    get_diff_stats,
    get_file_diffs,
    get_ref_display_name,
    resolve_ref,
    validate_repo,
)
from releasewave.llm import analyze_changes, render_changelogs
from releasewave.models import (
    AudienceType,
    ReleaseChangelog,
)
from releasewave.output import (
    print_changelogs,
    print_summary,
    update_changelog_file,
    write_changelogs,
)

console = Console(stderr=True)

# ── App Setup ────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="releasewave",
    help="🌊 AI-powered changelog generator that reads actual code diffs.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
    pretty_exceptions_enable=True,
)


# ── Version Callback ────────────────────────────────────────────────────────

def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]🌊 ReleaseWave[/bold cyan] v{__version__}")
        raise typer.Exit()


# ── Main Generate Command ───────────────────────────────────────────────────

@app.command(name="generate", help="Generate changelogs between two git refs.")
def generate(
    from_ref: str = typer.Argument(
        ...,
        help="Starting git ref (tag, branch, or commit SHA)",
    ),
    to_ref: str = typer.Argument(
        ...,
        help="Ending git ref (tag, branch, or commit SHA). Use HEAD for latest.",
    ),
    # ── Model Options ──
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="LLM model to use (LiteLLM format, e.g. gpt-4o-mini, gemini/gemini-2.5-flash)",
        rich_help_panel="LLM Options",
    ),
    # ── Output Options ──
    output_dir: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Output directory for generated files",
        rich_help_panel="Output Options",
    ),
    audiences: Optional[str] = typer.Option(
        None,
        "--audiences", "-a",
        help="Comma-separated audience types: developer,user,tweet",
        rich_help_panel="Output Options",
    ),
    format: Optional[str] = typer.Option(
        None,
        "--format", "-f",
        help="Output format: markdown, json, text",
        rich_help_panel="Output Options",
    ),
    update_changelog: bool = typer.Option(
        False,
        "--update-changelog/--no-update-changelog",
        help="Prepend to existing CHANGELOG.md",
        rich_help_panel="Output Options",
    ),
    no_stdout: bool = typer.Option(
        False,
        "--quiet", "-q",
        help="Suppress stdout output (only write files)",
        rich_help_panel="Output Options",
    ),
    json_export: bool = typer.Option(
        False,
        "--json",
        help="Also export full analysis as JSON",
        rich_help_panel="Output Options",
    ),
    # ── Repository Options ──
    repo: Optional[str] = typer.Option(
        None,
        "--repo", "-r",
        help="Path to git repository (default: current directory)",
        rich_help_panel="Repository Options",
    ),
    # ── Meta Options ──
    version: Optional[bool] = typer.Option(
        None,
        "--version", "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """
    🌊 Generate AI-powered changelogs from git diffs.

    Analyzes actual code changes (not just commit messages) between two git refs
    and generates developer, user-facing, and tweet-sized changelogs.

    Examples:
        releasewave generate v1.0.0 v1.1.0
        releasewave generate main HEAD --model gpt-4o-mini
        releasewave generate v2.0 v2.1 --audiences developer,tweet -o ./docs
    """
    # ── Banner ──
    _print_banner()

    # ── Resolve repo path ──
    repo_path = Path(repo) if repo else Path.cwd()
    repo_root = validate_repo(repo_path)
    console.print(f"  [dim]Repository: {repo_root}[/dim]")

    # ── Load config ──
    cli_overrides = {
        "model": model,
        "output_dir": output_dir,
        "audiences": audiences.split(",") if audiences else None,
        "format": format,
        "update_changelog": update_changelog,
        "no_stdout": no_stdout,
    }
    config = load_config(repo_root, cli_overrides)
    console.print(f"  [dim]Model: {config.llm.model}[/dim]")

    # ── Resolve refs ──
    console.print("\n[bold]📌 Resolving refs...[/bold]")

    if not from_ref or not from_ref.strip():
        console.print("[red]✗ Error: from_ref is empty.[/red]")
        console.print(
            "[dim]This usually happens on the first release when no previous tag exists.\n"
            "  Tip: Specify a starting ref manually, e.g.:\n"
            "    releasewave generate $(git rev-list --max-parents=0 HEAD) HEAD[/dim]"
        )
        raise typer.Exit(1)

    sha_from = resolve_ref(repo_root, from_ref)
    sha_to = resolve_ref(repo_root, to_ref)

    display_from = get_ref_display_name(repo_root, sha_from)
    display_to = get_ref_display_name(repo_root, sha_to)
    console.print(f"  {display_from} ({sha_from[:7]}) → {display_to} ({sha_to[:7]})")

    # ── Check for monorepo ──
    mono = detect_monorepo(repo_root, config)
    if mono.is_monorepo:
        console.print(
            f"\n[bold]📦 Monorepo detected:[/bold] {len(mono.packages)} packages"
        )
        for pkg in mono.packages:
            console.print(f"  • {pkg.name} ({pkg.path})")

    # ── Extract commits ──
    console.print("\n[bold]📝 Extracting commits...[/bold]")
    commits = get_commits(repo_root, sha_from, sha_to)
    console.print(f"  Found {len(commits)} commits")

    if not commits:
        console.print("[yellow]⚠ No commits found between these refs.[/yellow]")
        console.print("[dim]Tip: Make sure the from_ref is older than to_ref.[/dim]")
        raise typer.Exit(1)

    # ── Extract diffs ──
    console.print("\n[bold]📂 Extracting diffs...[/bold]")
    all_diffs = get_file_diffs(repo_root, sha_from, sha_to, config)
    
    if mono.is_monorepo:
        # Process each package
        for pkg in mono.packages:
            # Assumes pkg.path uses forward slashes (standardized relative paths)
            pkg_diffs = [d for d in all_diffs if d.path.startswith(pkg.path + "/")]
            if not pkg_diffs:
                continue
            
            console.print(f"\n[bold magenta]📦 Processing package: {pkg.name}[/bold magenta]")
            pkg_commits = get_commits(repo_root, sha_from, sha_to, path=pkg.path)
            if not pkg_commits:
                # Fallback to global commits if no package-specific commits found
                pkg_commits = commits

            _process_target(
                commits=pkg_commits, diffs=pkg_diffs, config=config,
                display_from=display_from, display_to=display_to,
                json_export=json_export, no_stdout=no_stdout, repo_root=repo_root,
                out_subdir=pkg.path
            )
            
        # Process root/global changes not belonging to any package
        root_diffs = [
            d for d in all_diffs 
            if not any(d.path.startswith(pkg.path + "/") for pkg in mono.packages)
        ]
        if root_diffs:
            console.print(f"\n[bold magenta]🌍 Processing root/global changes[/bold magenta]")
            _process_target(
                commits=commits, diffs=root_diffs, config=config,
                display_from=display_from, display_to=display_to,
                json_export=json_export, no_stdout=no_stdout, repo_root=repo_root,
                out_subdir=None
            )
    else:
        _process_target(
            commits=commits, diffs=all_diffs, config=config,
            display_from=display_from, display_to=display_to,
            json_export=json_export, no_stdout=no_stdout, repo_root=repo_root,
            out_subdir=None
        )

    console.print(
        f"\n[bold green]✓ Done![/bold green] "
        f"Generated changelog(s) in {config.output.directory}"
    )


def _process_target(commits, diffs, config, display_from, display_to, json_export, no_stdout, repo_root, out_subdir):
    """Helper to process diffs and generate output for a specific Target/Package."""
    stats = get_diff_stats(diffs)
    console.print(
        f"  {stats['total_files']} files: "
        f"[green]+{stats['files_added']}[/green] added, "
        f"[yellow]~{stats['files_modified']}[/yellow] modified, "
        f"[red]-{stats['files_deleted']}[/red] deleted"
    )
    console.print(
        f"  [green]+{stats['total_additions']}[/green] / "
        f"[red]-{stats['total_deletions']}[/red] lines"
    )

    # ── LLM Analysis ──
    console.print("\n[bold]🤖 Analyzing with LLM...[/bold]")
    try:
        analysis = analyze_changes(commits, diffs, config)
    except RuntimeError as e:
        console.print(f"\n[red]✗ LLM analysis failed: {e}[/red]")
        console.print("[yellow]Falling back to commit-message-only mode...[/yellow]")
        # Fall back to commit-only analysis
        from releasewave.llm import _analyze_commits_only
        from releasewave.chunker import format_commits_for_llm
        commit_log = format_commits_for_llm(commits)
        analysis = _analyze_commits_only(commits, commit_log, config)

    console.print(
        f"  Detected [bold]{len(analysis.changes)}[/bold] changes across "
        f"{len(set(c.category for c in analysis.changes))} categories"
    )

    # ── Render Changelogs ──
    console.print("\n[bold]📝 Rendering changelogs...[/bold]")
    changelogs = render_changelogs(analysis, display_from, display_to, config)

    # ── Build Release Object ──
    release = ReleaseChangelog(
        version_from=display_from,
        version_to=display_to,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_used=config.llm.model,
        total_commits=len(commits),
        total_files_changed=stats["total_files"],
        analysis=analysis,
        changelogs=changelogs,
    )

    # ── Write Files ──
    console.print("\n[bold]💾 Writing files...[/bold]")
    
    # Adjust output path if inside a monorepo package
    target_out_dir = Path(config.output.directory)
    if out_subdir:
        target_out_dir = target_out_dir / out_subdir

    written = write_changelogs(
        release,
        output_dir=str(target_out_dir),
        write_json=json_export,
    )

    # ── Update CHANGELOG.md ──
    if config.output.update_changelog:
        dev_changelog = next(
            (cl for cl in changelogs if cl.audience == AudienceType.DEVELOPER),
            None,
        )
        if dev_changelog:
            update_changelog_file(
                dev_changelog.content,
                config.output.changelog_file,
                repo_root if not out_subdir else repo_root / out_subdir,
            )

    # ── Print to stdout ──
    if config.output.stdout and not no_stdout:
        console.print()
        print_changelogs(changelogs)

    # ── Summary ──
    console.print()
    print_summary(release)


# ── Init Command ─────────────────────────────────────────────────────────────

@app.command(name="init", help="Create a .rwave.yml configuration file.")
def init(
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing config file",
    ),
) -> None:
    """
    Create a .rwave.yml configuration file in the current directory.
    """
    _print_banner()

    config_path = Path.cwd() / ".rwave.yml"

    if config_path.exists() and not force:
        console.print(
            "[yellow]⚠ .rwave.yml already exists.[/yellow] "
            "Use --force to overwrite."
        )
        raise typer.Exit(1)

    config_content = generate_example_config()
    config_path.write_text(config_content, encoding="utf-8")
    console.print(f"[green]✓[/green] Created [bold].rwave.yml[/bold]")
    console.print("[dim]Edit this file to customize ReleaseWave settings.[/dim]")


# ── Models Command ────────────────────────────────────────────────────────────

@app.command(name="models", help="Show recommended LLM models.")
def models() -> None:
    """Show a list of recommended LLM models for use with ReleaseWave."""
    _print_banner()

    models_info = """
[bold]Recommended Models (via LiteLLM):[/bold]

[bold cyan]Budget-Friendly (Default):[/bold cyan]
  • gemini/gemini-2.5-flash      — Google Gemini 2.0 Flash (fast, cheap)
  • gpt-4o-mini                  — OpenAI GPT-4o Mini

[bold cyan]High Quality:[/bold cyan]
  • gpt-4o                       — OpenAI GPT-4o
  • claude-sonnet-4-20250514     — Anthropic Claude Sonnet
  • gemini/gemini-2.5-pro        — Google Gemini 2.5 Pro

[bold cyan]Local (Free):[/bold cyan]
  • ollama/llama3                — Llama 3 via Ollama
  • ollama/codellama             — CodeLlama via Ollama
  • ollama/mistral               — Mistral via Ollama

[bold cyan]OpenRouter (Any Model):[/bold cyan]
  • openrouter/<model-name>      — Any model on OpenRouter

[bold]Environment Variables:[/bold]
  Set your API key via environment variable:
  • OPENAI_API_KEY       for OpenAI models
  • GEMINI_API_KEY       for Google Gemini
  • ANTHROPIC_API_KEY    for Claude
  • OPENROUTER_API_KEY   for OpenRouter
  • (no key needed)      for local Ollama models

  Or use RWAVE_API_KEY to set a universal key.
"""
    console.print(models_info)


# ── Helpers ──────────────────────────────────────────────────────────────────

BANNER = r"""[bold cyan]
    ____       __                __          __
   / __ \___  / /__  ____ ______/__\ _    __/ /___ __   _____
  / /_/ / _ \/ / _ \/ __ `/ ___/ _ \ | /| / / __ `/ | / / _ \
 / _, _/  __/ /  __/ /_/ (__  )  __/ |/ |/ / /_/ /| |/ /  __/
/_/ |_|\___/_/\___/\__,_/____/\___/|__/|__/\__,_/ |___/\___/
[/bold cyan]"""


def _print_banner() -> None:
    """Print the ReleaseWave ASCII banner."""
    console.print(BANNER)
    console.print(f"  [dim]v{__version__} — AI-powered changelog generator[/dim]\n")


# ── Default command mapping ──────────────────────────────────────────────────
# Make `releasewave <from> <to>` work as a shortcut for `releasewave generate <from> <to>`

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version", "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """
    🌊 ReleaseWave — AI-powered changelog generator.

    Reads actual code diffs, works on messy commits, generates
    multi-audience changelogs in a single command.

    Quick start:
        releasewave generate v1.0 v1.1
        releasewave init
    """
    pass
