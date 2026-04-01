"""
Tests for socialosintagent/chatops.py — build_agent and analyze_target.

Covers:
- analyze_target: validates platform availability
- analyze_target: validates platform in FETCHERS
- analyze_target: validates non-empty platform and username
- analyze_target: validates non-empty query
- analyze_target: uses default query when none provided
- analyze_target: calls agent.analyze with correct args
- build_agent: constructs SocialOSINTAgent with correct args
"""

import argparse
import pytest
from unittest.mock import MagicMock, patch

from socialosintagent.chatops import (
    DEFAULT_ANALYSIS_QUERY,
    analyze_target,
    build_agent,
)


class TestAnalyzeTarget:
    def test_raises_on_empty_platform(self):
        agent = MagicMock()
        with pytest.raises(ValueError, match="non-empty"):
            analyze_target(agent, "", "alice")

    def test_raises_on_empty_username(self):
        agent = MagicMock()
        with pytest.raises(ValueError, match="non-empty"):
            analyze_target(agent, "twitter", "  ")

    def test_raises_on_unavailable_platform(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        with pytest.raises(RuntimeError, match="not available"):
            analyze_target(agent, "twitter", "alice")

    def test_raises_on_unsupported_fetcher(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = [
            "twitter",
            "github",
            "hackernews",
        ]
        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            with pytest.raises(RuntimeError, match="not currently supported"):
                analyze_target(agent, "twitter", "alice")

    def test_raises_on_empty_query(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            with pytest.raises(ValueError, match="query must be non-empty"):
                analyze_target(agent, "github", "bob", query="   ")

    def test_uses_default_query_when_none(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        agent.analyze.return_value = {"report": "done"}

        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            result = analyze_target(agent, "github", "bob")

        agent.analyze.assert_called_once()
        call_args = agent.analyze.call_args
        assert call_args[0][1] == DEFAULT_ANALYSIS_QUERY

    def test_passes_custom_query(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        agent.analyze.return_value = {"report": "done"}

        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            result = analyze_target(agent, "github", "bob", query="Custom analysis")

        call_args = agent.analyze.call_args
        assert call_args[0][1] == "Custom analysis"

    def test_passes_force_refresh(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        agent.analyze.return_value = {"report": "done"}

        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            analyze_target(agent, "github", "bob", force_refresh=True)

        call_args = agent.analyze.call_args
        assert call_args.kwargs.get("force_refresh") is True or (
            len(call_args.args) > 2 and call_args.args[2] is True
        )

    def test_passes_fetch_options(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        agent.analyze.return_value = {"report": "done"}

        opts = {"default_count": 100, "targets": {}}
        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            analyze_target(agent, "github", "bob", fetch_options=opts)

        call_args = agent.analyze.call_args
        assert call_args.kwargs.get("fetch_options") == opts or (
            len(call_args.args) > 3 and call_args.args[3] == opts
        )

    def test_returns_analyze_result(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        expected = {"report": "analysis result", "error": False}
        agent.analyze.return_value = expected

        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            result = analyze_target(agent, "github", "bob")

        assert result == expected

    def test_platform_lowercased(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        agent.analyze.return_value = {"report": "done"}

        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            analyze_target(agent, "GitHub", "bob")

        call_args = agent.analyze.call_args
        assert call_args[0][0] == {"github": ["bob"]}

    def test_username_sanitized(self):
        agent = MagicMock()
        agent.client_manager.get_available_platforms.return_value = ["github"]
        agent.analyze.return_value = {"report": "done"}

        with patch("socialosintagent.chatops.FETCHERS", {"github": MagicMock()}):
            analyze_target(agent, "github", "  bob  ")

        call_args = agent.analyze.call_args
        target_spec = call_args[0][0]
        assert target_spec["github"] == ["bob"]


class TestBuildAgent:
    @patch("socialosintagent.chatops.ClientManager")
    @patch("socialosintagent.chatops.LLMAnalyzer")
    @patch("socialosintagent.chatops.CacheManager")
    @patch("socialosintagent.chatops.SocialOSINTAgent")
    def test_constructs_agent_with_offline_false(
        self, mock_agent_cls, mock_cache_cls, mock_llm_cls, mock_cm_cls
    ):
        build_agent(offline=False)
        mock_agent_cls.assert_called_once()
        args = mock_agent_cls.call_args[0][0]
        assert args.offline is False

    @patch("socialosintagent.chatops.ClientManager")
    @patch("socialosintagent.chatops.LLMAnalyzer")
    @patch("socialosintagent.chatops.CacheManager")
    @patch("socialosintagent.chatops.SocialOSINTAgent")
    def test_constructs_agent_with_offline_true(
        self, mock_agent_cls, mock_cache_cls, mock_llm_cls, mock_cm_cls
    ):
        build_agent(offline=True)
        args = mock_agent_cls.call_args[0][0]
        assert args.offline is True


class TestDefaultAnalysisQuery:
    def test_default_query_is_non_empty(self):
        assert DEFAULT_ANALYSIS_QUERY.strip() != ""

    def test_default_query_mentions_osint(self):
        assert "OSINT" in DEFAULT_ANALYSIS_QUERY
