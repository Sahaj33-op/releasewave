"""Tests for the LLM integration layer.

Covers:
- async_call_llm with mocked litellm.acompletion
- instructor-based structured output (response_model)
- Retry & exponential backoff
- run_async event loop safety
- Cache path resolution
- _process_chunk_async caching logic
- analyze_changes routing (0 chunks, 1 chunk, N chunks)
- render_changelogs audience dispatch

NOTE: litellm has a known circular import issue in test environments.
      We mock the litellm symbols at the `releasewave.llm` module level
      to isolate tests from the actual provider SDK.
"""

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from releasewave.config import ReleaseWaveConfig
from releasewave.models import (
    AnalysisResult,
    ChangeCategory,
    ChangeEntry,
    ChangeImpact,
    ChangelogOutput,
    CommitInfo,
    DiffChunk,
    FileDiff,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def config(tmp_path):
    """Default test config with repo_root pointing to a temp dir."""
    cfg = ReleaseWaveConfig()
    cfg.repo_root = tmp_path
    cfg.llm.max_retries = 2
    cfg.llm.timeout = 10
    return cfg


@pytest.fixture
def sample_analysis():
    """A minimal AnalysisResult for mocking LLM returns."""
    return AnalysisResult(
        changes=[
            ChangeEntry(
                category=ChangeCategory.FEATURE,
                impact=ChangeImpact.HIGH,
                title="Add dark mode",
                description="Dark mode toggle in settings.",
                files=["src/settings.py"],
            )
        ],
        summary="Added dark mode.",
        highlights=["Dark mode support"],
    )


@pytest.fixture
def mock_acompletion_response():
    """A mock LiteLLM acompletion response object."""
    mock_msg = MagicMock()
    mock_msg.content = '{"result": "ok"}'
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def _get_llm_module():
    """Import releasewave.llm with litellm symbols already mocked to avoid circular imports."""
    import releasewave.llm as llm_mod
    return llm_mod


# ── async_call_llm ───────────────────────────────────────────────────────────

class TestAsyncCallLLM:
    """Test the core async LLM call function."""

    async def test_plain_text_response(self, config, mock_acompletion_response):
        """acompletion returns text when no response_model is set."""
        llm = _get_llm_module()

        mock_ac = AsyncMock(return_value=mock_acompletion_response)
        with patch.object(llm, "acompletion", mock_ac):
            result = await llm.async_call_llm(
                messages=[{"role": "user", "content": "hello"}],
                config=config,
            )
            assert result == '{"result": "ok"}'
            mock_ac.assert_awaited_once()

    async def test_structured_output_via_instructor(self, config, sample_analysis):
        """When response_model is set, instructor client handles the call."""
        llm = _get_llm_module()

        mock_create = AsyncMock(return_value=sample_analysis)
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create

        mock_instructor = MagicMock()
        mock_instructor.from_litellm.return_value = mock_client

        with patch.dict("sys.modules", {"instructor": mock_instructor}):
            with patch.object(llm, "acompletion", AsyncMock()):
                result = await llm.async_call_llm(
                    messages=[{"role": "user", "content": "analyze"}],
                    config=config,
                    response_model=AnalysisResult,
                )
                assert isinstance(result, AnalysisResult)
                assert result.summary == "Added dark mode."
                mock_create.assert_awaited_once()

    async def test_retry_on_failure(self, config):
        """Retries on failure with exponential backoff."""
        llm = _get_llm_module()
        config.llm.max_retries = 2

        mock_msg = MagicMock()
        mock_msg.content = "success"
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        mock_ac = AsyncMock(side_effect=[ValueError("transient error"), mock_resp])

        with patch.object(llm, "acompletion", mock_ac):
            with patch.object(llm.asyncio, "sleep", new_callable=AsyncMock):
                result = await llm.async_call_llm(
                    messages=[{"role": "user", "content": "test"}],
                    config=config,
                )
                assert result == "success"
                assert mock_ac.await_count == 2

    async def test_all_retries_exhausted(self, config):
        """Raises RuntimeError after all retries fail."""
        llm = _get_llm_module()
        config.llm.max_retries = 2

        mock_ac = AsyncMock(side_effect=ValueError("persistent error"))

        with patch.object(llm, "acompletion", mock_ac):
            with patch.object(llm.asyncio, "sleep", new_callable=AsyncMock):
                with pytest.raises(RuntimeError, match="LLM call failed after 2 attempts"):
                    await llm.async_call_llm(
                        messages=[{"role": "user", "content": "test"}],
                        config=config,
                    )

    async def test_empty_response_raises(self, config):
        """Empty LLM response triggers retry and then fails."""
        llm = _get_llm_module()
        config.llm.max_retries = 1

        mock_msg = MagicMock()
        mock_msg.content = ""
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        mock_ac = AsyncMock(return_value=mock_resp)

        with patch.object(llm, "acompletion", mock_ac):
            with pytest.raises(RuntimeError, match="LLM call failed"):
                await llm.async_call_llm(
                    messages=[{"role": "user", "content": "test"}],
                    config=config,
                )


# ── run_async ────────────────────────────────────────────────────────────────

class TestRunAsync:
    """Test the event loop safety wrapper."""

    def test_run_async_no_existing_loop(self):
        """Works when no event loop is running."""
        llm = _get_llm_module()

        async def simple():
            return 42

        assert llm.run_async(simple()) == 42

    def test_run_async_from_within_loop(self):
        """Handles being called from within a running event loop."""
        llm = _get_llm_module()

        async def inner():
            return "nested"

        async def outer():
            return llm.run_async(inner())

        # This should NOT crash with "cannot be called from a running event loop"
        result = asyncio.run(outer())
        assert result == "nested"


# ── Cache Path Resolution ────────────────────────────────────────────────────

class TestCachePath:
    """Test cache path resolution logic."""

    def test_cache_path_uses_repo_root(self, config, tmp_path):
        """Cache is created under repo_root/.rwave/cache, not CWD."""
        llm = _get_llm_module()

        cache_path = llm._get_cache_path(config, "test-content")
        assert str(tmp_path) in str(cache_path)
        assert ".rwave" in str(cache_path)
        assert cache_path.parent.exists()

    def test_cache_path_deterministic(self, config):
        """Same content always produces the same cache path."""
        llm = _get_llm_module()

        p1 = llm._get_cache_path(config, "same-content")
        p2 = llm._get_cache_path(config, "same-content")
        assert p1 == p2

    def test_cache_path_differs_per_content(self, config):
        """Different content produces different cache paths."""
        llm = _get_llm_module()

        p1 = llm._get_cache_path(config, "content-a")
        p2 = llm._get_cache_path(config, "content-b")
        assert p1 != p2

    def test_cache_path_fallback_to_cwd(self):
        """Falls back to CWD if repo_root is None."""
        llm = _get_llm_module()

        cfg = ReleaseWaveConfig()
        cfg.repo_root = None
        cache_path = llm._get_cache_path(cfg, "test")
        assert ".rwave" in str(cache_path)


# ── _process_chunk_async Caching ─────────────────────────────────────────────

class TestProcessChunkAsync:
    """Test the per-chunk async processor with caching."""

    async def test_cache_hit_skips_llm(self, config, sample_analysis):
        """If a cache file exists, LLM is not called."""
        llm = _get_llm_module()

        chunk = DiffChunk(
            chunk_id=1,
            files=[
                FileDiff(path="a.py", change_type="M", diff_content="+ line")
            ],
            estimated_tokens=10,
        )

        # Pre-populate the cache
        from releasewave.chunker import format_chunk_for_llm
        from releasewave.prompts import build_analysis_prompt

        diff_content = format_chunk_for_llm(chunk)
        messages = build_analysis_prompt(diff_content=diff_content, commit_log="test log")
        cache_key = json.dumps(messages)
        cache_path = llm._get_cache_path(config, cache_key)
        cache_path.write_text(
            json.dumps(sample_analysis.model_dump(), default=str),
            encoding="utf-8",
        )

        mock_llm_call = AsyncMock()
        with patch.object(llm, "async_call_llm", mock_llm_call):
            result = await llm._process_chunk_async(1, 1, chunk, "test log", config)
            mock_llm_call.assert_not_awaited()  # Cache hit => no LLM call
            assert isinstance(result, AnalysisResult)
            assert result.summary == "Added dark mode."

    async def test_cache_miss_calls_llm_and_writes_cache(self, config, sample_analysis):
        """On cache miss, calls LLM and writes the result to disk."""
        llm = _get_llm_module()

        chunk = DiffChunk(
            chunk_id=1,
            files=[
                FileDiff(path="b.py", change_type="A", diff_content="+ new file")
            ],
            estimated_tokens=10,
        )

        mock_llm_call = AsyncMock(return_value=sample_analysis)
        with patch.object(llm, "async_call_llm", mock_llm_call):
            result = await llm._process_chunk_async(1, 1, chunk, "test log", config)

            mock_llm_call.assert_awaited_once()
            assert result.summary == "Added dark mode."

            # Verify cache was written
            from releasewave.chunker import format_chunk_for_llm
            from releasewave.prompts import build_analysis_prompt

            diff_content = format_chunk_for_llm(chunk)
            messages = build_analysis_prompt(diff_content=diff_content, commit_log="test log")
            cache_path = llm._get_cache_path(config, json.dumps(messages))
            assert cache_path.exists()


# ── analyze_changes Routing ──────────────────────────────────────────────────

class TestAnalyzeChanges:
    """Test the high-level analysis pipeline routing."""

    def test_no_diffs_falls_back_to_commits(self, config, sample_analysis):
        """When diffs are empty, uses commit-only analysis."""
        llm = _get_llm_module()

        commits = [
            CommitInfo(
                sha="abc123",
                short_sha="abc",
                message="feat: add X",
                subject="feat: add X",
                author_name="Test",
                author_email="t@t.com",
                timestamp="2026-01-01T00:00:00Z",
            )
        ]
        with patch.object(llm, "call_llm", return_value=sample_analysis):
            result = llm.analyze_changes(commits, [], config)
            assert isinstance(result, AnalysisResult)

    def test_single_chunk_direct_analysis(self, config, sample_analysis):
        """Single chunk uses _analyze_single_chunk."""
        llm = _get_llm_module()

        commits = [
            CommitInfo(
                sha="abc123",
                short_sha="abc",
                message="feat: add X",
                subject="feat: add X",
                author_name="Test",
                author_email="t@t.com",
                timestamp="2026-01-01T00:00:00Z",
            )
        ]
        diffs = [
            FileDiff(path="main.py", change_type="M", diff_content="+ line")
        ]
        with patch.object(llm, "call_llm", return_value=sample_analysis):
            result = llm.analyze_changes(commits, diffs, config)
            assert isinstance(result, AnalysisResult)


# ── Render Changelogs ────────────────────────────────────────────────────────

class TestRenderChangelogs:
    """Test audience-specific rendering."""

    def test_renders_all_configured_audiences(self, config, sample_analysis):
        """Generates one changelog per configured audience."""
        llm = _get_llm_module()
        config.output.audiences = ["developer", "user", "tweet"]

        with patch.object(llm, "call_llm", return_value="# Changelog content"):
            results = llm.render_changelogs(sample_analysis, "v1.0", "v1.1", config)
            assert len(results) == 3
            audience_types = {r.audience.value for r in results}
            assert audience_types == {"developer", "user", "tweet"}

    def test_skips_unknown_audience(self, config, sample_analysis):
        """Unknown audience keys are skipped with a warning."""
        llm = _get_llm_module()
        config.output.audiences = ["developer", "invalid_audience"]

        with patch.object(llm, "call_llm", return_value="# Content"):
            results = llm.render_changelogs(sample_analysis, "v1.0", "v1.1", config)
            assert len(results) == 1
