# RELEASEWAVE
### AI-Powered Changelog Generator
**Product Requirements Document · v1.0 · March 2026**

---

| Field | Detail |
|---|---|
| Status | Draft — In Review |
| Owner | Sahaj (SSASIT CE) |
| Target Launch | 45 days from kickoff |
| Stack | Python, CLI, GitHub Actions, LLM APIs |
| License | MIT (Open Source) |
| Goal | 5,000+ GitHub stars within 90 days of launch |

---

## 1. Executive Summary

ReleaseWave is an open-source, LLM-powered changelog generator that works on any repository — regardless of commit quality, message format, or team discipline. Unlike every existing tool in this space, it reads actual code diffs rather than commit messages alone, generates multiple audience-targeted changelog versions in a single pass, and requires zero configuration to get started.

The existing tools (git-cliff, conventional-changelog, release-please) all share the same fatal flaw: they demand clean, conventional commit discipline. Real-world teams don't have that. ReleaseWave solves the problem that actually exists.

---

## 2. Problem Statement

### 2.1 What Exists Today

The current changelog generation landscape has three categories of tools, all with the same core limitation:

- **git-cliff** — Fast, Rust-based, highly configurable. But 100% dependent on conventional commit format. Garbage commits produce garbage output.
- **conventional-changelog / standard-version** — Same problem. Requires `feat:`, `fix:`, `chore:` prefixes. Breaks on any non-standard commit.
- **release-please (Google)** — Automated GitHub Action. Again, strictly conventional commits. Entire PRs get missed if the commit message is ambiguous.
- **Manual changelogs** — Most teams still write these by hand. Slow, inconsistent, always incomplete.

### 2.2 The Real Pain

Four distinct problems no existing tool addresses simultaneously:

- **Messy commits are the norm.** `wip`, `fix`, `update stuff`, `lol` — real repos are full of these. No tool interprets them intelligently.
- **One changelog, wrong audience.** A technical diff log means nothing to end users. A plain-English summary confuses developers who need specifics. No tool generates per-audience output.
- **Commit messages lie.** A commit titled "minor fix" might contain a breaking API change. Reading the actual diff catches what the message misses.
- **Monorepo chaos.** Separate changelogs for multiple packages in one repo is a documented open problem across all major tools.

---

## 3. Solution — ReleaseWave

### 3.1 Core Concept

ReleaseWave uses an LLM to analyze both commit messages AND actual code diffs between two git refs (tags, branches, commits). It produces three distinct changelog versions in one command, requiring no prior commit discipline from the team.

### 3.2 Unique Selling Points

| Existing Tools | ReleaseWave |
|---|---|
| Requires conventional commits | **Works on any commit style** |
| Reads commit messages only | **Reads actual code diffs** |
| Single output format | **3 audience versions per run** |
| Broken monorepo support | **Native monorepo support** |
| Config required before use | **Zero config, one command** |

---

## 4. Target Users

### 4.1 Solo Developers & Open Source Maintainers
- **Pain:** Hate writing changelogs. Skip it entirely or do it sloppily before a release.
- **Need:** One command that generates something usable in under 10 seconds.
- **Star trigger:** Immediately solves a task they actively dread.

### 4.2 Engineering Teams at Startups
- **Pain:** No commit discipline enforced. Need changelogs for product, docs, and release notes.
- **Need:** Something that works despite the chaos, generates per-audience output.
- **Star trigger:** Saves 30–60 minutes per release without enforcing process changes.

### 4.3 DevOps / Platform Engineers
- **Pain:** Need changelog generation as part of a CI/CD pipeline without manual steps.
- **Need:** GitHub Action with configurable output, multiple LLM provider support.
- **Star trigger:** Drop-in GitHub Action that just works.

---

## 5. Feature Specification

### 5.1 MVP Features (v1.0 — 30 days)

| Feature | Description | Priority |
|---|---|---|
| Diff-aware analysis | Read git diffs between two refs, not just commit messages | P0 |
| Messy commit handling | LLM interprets ambiguous/bad commits into meaningful entries | P0 |
| 3-audience output | Developer changelog, user-facing notes, tweet-sized announcement | P0 |
| Zero config mode | Works with just `releasewave v1.0 v1.1` — no setup | P0 |
| Multi-LLM support | OpenAI, Gemini, Claude, OpenRouter, local Ollama | P0 |
| Markdown output | Clean `.md` files with proper sections and formatting | P0 |
| CLI interface | Full-featured CLI with flags for ref range, model, output format | P1 |
| GitHub Action | Drop-in `.github/workflows` action for automated release notes | P1 |
| Monorepo support | Detect packages, generate per-package changelogs | P1 |
| Config file (`.rwave.yml`) | Optional config for persistent settings, custom prompts | P1 |

### 5.2 Post-MVP Features (v1.1 — 60+ days)

| Feature | Description | Priority |
|---|---|---|
| PR body generation | Auto-generate PR descriptions from diff analysis | P2 |
| Changelog web viewer | Hosted mini-site for browsing versioned changelogs | P2 |
| Slack/Discord webhook | Post changelog summary to team channels on release | P2 |
| Custom audience profiles | Define your own audience + tone via config | P2 |
| Changelog diff scoring | Score how complete/accurate a manually written changelog is | P2 |

---

## 6. Technical Architecture

### 6.1 Stack

| Component | Choice |
|---|---|
| Language | Python 3.10+ |
| CLI framework | Typer (fast, clean, type-safe) |
| Git integration | GitPython + subprocess git diff |
| LLM layer | LiteLLM (unified interface for all providers) |
| Output formats | Markdown, JSON (structured), plain text |
| CI/CD | GitHub Actions (composite action) |
| Config | YAML via PyYAML, auto-detected `.rwave.yml` |
| Distribution | PyPI (`pip install releasewave`) |

### 6.2 Core Pipeline

1. **Ref resolution** — Parse the two git refs (tags, branches, SHAs) passed by the user.
2. **Diff extraction** — Run `git diff` between refs, filter by file type, chunk into token-safe segments.
3. **Commit log extraction** — Pull all commits in range with messages, authors, timestamps.
4. **LLM analysis** — Send diff chunks + commit log to LLM with structured prompt. Extract categorized changes (features, fixes, breaking, internal).
5. **Audience rendering** — Run three separate rendering prompts — technical, user-facing, tweet.
6. **Output** — Write markdown files, optionally update `CHANGELOG.md`, print to stdout.

### 6.3 Key Technical Decisions

- **LiteLLM over direct SDK** — Single interface handles provider switching, fallbacks, and local models without code changes.
- **Chunking strategy** — Large diffs get split by file, analyzed per-chunk, then merged — avoids context window exhaustion.
- **Token budget enforcement** — Hard limits per component prevent runaway costs on large repos.
- **Streaming output** — Stream LLM responses to stdout so the CLI feels fast even on large diffs.

### 6.4 Edge Cases & Failure Modes

- **Binary files in diff** — Filter out, note "binary file changed" in output.
- **Massive diffs (1000+ files)** — Chunk by directory, generate per-directory summaries first.
- **LLM API failure** — Graceful fallback to commit-message-only mode with a warning.
- **No commits in range** — Clear error with suggested correct syntax.
- **Rate limiting** — Exponential backoff with configurable retry count.

---

## 7. Go-to-Market & Star Strategy

### Phase 1 — Build in Public (Days 1–30)
- Daily progress posts on Twitter/X with technical depth — show the diff-reading approach, not just the output.
- Build the GitHub README as a marketing page first. Demo GIF in first scroll. One-liner install. Three outputs side-by-side.
- Record a 60-second terminal demo video showing the zero-config experience.

### Phase 2 — Launch (Day 30)
- **Hacker News:** Show HN post. Timing: Tuesday/Wednesday 9am EST. Title: *"ReleaseWave: AI changelog generator that works on messy commits and reads actual diffs"*
- **Reddit:** r/Python, r/programming, r/devops — genuine posts showing the problem, not just self-promo.
- **Dev.to / Hashnode article:** *"Why every changelog tool is broken (and how we fixed it)"*
- **Product Hunt launch** — coordinate upvotes, have 10 people ready to comment on day one.

### Phase 3 — Growth (Days 30–90)
- Add ReleaseWave to `awesome-python`, `awesome-cli-apps`, `awesome-github-actions` lists.
- Reach out to 10 mid-sized open source projects and offer to generate their next changelog for free.
- Write a comparison post: *"ReleaseWave vs git-cliff vs conventional-changelog"* — capture that search traffic.

---

## 8. Success Metrics

| Milestone | Target |
|---|---|
| 30-day | 500+ GitHub stars, 200+ PyPI downloads/week |
| 60-day | 2,000+ stars, featured in one major newsletter |
| 90-day | 5,000+ stars — qualifies for Claude for Open Source |
| Quality signal | 10+ external contributors or issue reporters |
| Adoption signal | Used in 50+ public repos (track via GitHub search) |

---

## 9. Build Timeline

| Period | Milestone |
|---|---|
| Days 1–3 | Repo setup, README, architecture decisions, CLI scaffold |
| Days 4–10 | Core pipeline: git diff extraction, commit parsing, LLM integration |
| Days 11–17 | 3-audience output, monorepo support, zero-config mode |
| Days 18–22 | GitHub Action, config file support, PyPI packaging |
| Days 23–28 | Polish, edge cases, documentation, demo video |
| Day 30 | Public launch across all channels |
| Days 31–45 | Iterate on feedback, ship v1.1 features |

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM API costs | Default to cheapest model (Gemini Flash / GPT-4o-mini). Offer local Ollama support for cost-zero option. |
| Crowded space | USP is diff-reading + multi-audience angle. Make that the headline everywhere. |
| Quality variance | LLM output quality varies by model. Ship with prompt templates tested against 10+ real repos. |
| Low adoption | Plan A: HN launch. Plan B: Direct outreach to OSS maintainers. Plan C: Embed in popular GitHub Action templates. |
| Feature creep | Strictly enforce P0 scope for v1.0. Every non-P0 idea goes to GitHub Issues. |

---

*Document prepared by Sahaj · March 2026 · ReleaseWave v1.0 PRD*