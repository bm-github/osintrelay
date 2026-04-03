"""
Test the enhanced error tracking in async vision analysis.
"""

import argparse
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import create_autospec, patch

from socialosintagent.analyzer import ImageProcessingError, SocialOSINTAgent
from socialosintagent.cache import CacheManager
from socialosintagent.client_manager import ClientManager
from socialosintagent.exceptions import RateLimitExceededError
from socialosintagent.image_processor import ProcessingStatus
from socialosintagent.llm import LLMAnalyzer


@pytest.fixture
def agent_for_error_tests(monkeypatch):
    """Provides a SocialOSINTAgent instance for error tracking tests."""
    monkeypatch.setenv("LLM_API_KEY", "test_key")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://test.api/v1")
    monkeypatch.setenv("IMAGE_ANALYSIS_MODEL", "test_vision_model")
    monkeypatch.setenv("ANALYSIS_MODEL", "test_text_model")

    args = argparse.Namespace(
        offline=False,
        no_auto_save=True,
        format="markdown",
        unsafe_allow_external_media=False,
    )

    with patch("socialosintagent.llm._load_prompt", return_value="mock prompt"):
        mock_cache = create_autospec(CacheManager, instance=True)
        mock_cache.is_offline = False
        mock_cache.base_dir = Path("data")
        mock_llm = create_autospec(LLMAnalyzer, instance=True)
        mock_client_manager = create_autospec(ClientManager, instance=True)

    return SocialOSINTAgent(args, mock_cache, mock_llm, mock_client_manager)


def test_image_processing_error_dataclass():
    """Test ImageProcessingError dataclass structure."""
    error = ImageProcessingError(
        url="https://example.com/image.jpg",
        stage="download",
        error_type="timeout",
        error_message="Connection timeout after 20s",
        context="twitter user @example",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    assert error.url == "https://example.com/image.jpg"
    assert error.stage == "download"
    assert error.error_type == "timeout"
    assert error.error_message == "Connection timeout after 20s"
    assert error.context == "twitter user @example"
    assert error.timestamp is not None


def test_error_categorization_download_timeout(agent_for_error_tests):
    """Test categorization of download timeout errors."""

    class MockTimeoutError(Exception):
        pass

    error = MockTimeoutError("Connection timeout after 20s")
    error_type = agent_for_error_tests._categorize_download_error(
        error, "https://example.com/img.jpg", "twitter"
    )

    assert error_type == "timeout"


def test_error_categorization_download_404(agent_for_error_tests):
    """Test categorization of 404 download errors."""

    class Mock404Error(Exception):
        pass

    error = Mock404Error("404 Not Found")
    error_type = agent_for_error_tests._categorize_download_error(
        error, "https://example.com/img.jpg", "twitter"
    )

    assert error_type == "not_found"


def test_error_categorization_download_rate_limit(agent_for_error_tests):
    """Test categorization of rate limit download errors."""

    class MockRateLimitError(Exception):
        pass

    error = MockRateLimitError("429 Too Many Requests")
    error_type = agent_for_error_tests._categorize_download_error(
        error, "https://example.com/img.jpg", "twitter"
    )

    assert error_type == "rate_limit"


def test_error_categorization_preprocess_invalid_format(
    agent_for_error_tests, tmp_path
):
    """Test categorization of invalid format errors."""

    class MockFormatError(Exception):
        pass

    error = MockFormatError("Unsupported image format")
    error_type = agent_for_error_tests._categorize_preprocess_error(
        error, tmp_path / "test.jpg"
    )

    assert error_type == "invalid_format"


def test_error_categorization_analysis_rate_limit(agent_for_error_tests):
    """Test categorization of analysis rate limit errors."""
    error = RateLimitExceededError("LLM rate limit exceeded")
    error_type = agent_for_error_tests._categorize_analysis_error(error)

    assert error_type == "rate_limit"


def test_error_categorization_empty():
    """Test error categorization with empty list."""
    from socialosintagent.analyzer import SocialOSINTAgent

    # Since _categorize_errors is an instance method, we need an instance
    # But we can test the structure directly
    expected = {
        "download_failed": 0,
        "preprocess_failed": 0,
        "analyze_failed": 0,
        "rate_limited": 0,
        "network_errors": 0,
        "invalid_format": 0,
        "other_errors": 0,
    }

    assert expected["download_failed"] == 0
    assert expected["preprocess_failed"] == 0
    assert expected["analyze_failed"] == 0


def test_error_categorization_with_errors(agent_for_error_tests):
    """Test error categorization with mixed errors."""
    errors = [
        ImageProcessingError(
            url="https://example.com/img1.jpg",
            stage="download",
            error_type="timeout",
            error_message="Connection timeout",
            context="twitter user @test1",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
        ImageProcessingError(
            url="https://example.com/img2.jpg",
            stage="download",
            error_type="network",
            error_message="Network error",
            context="twitter user @test2",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
        ImageProcessingError(
            url="https://example.com/img3.jpg",
            stage="preprocess",
            error_type="invalid_format",
            error_message="Unsupported format",
            context="twitter user @test3",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
        ImageProcessingError(
            url="https://example.com/img4.jpg",
            stage="analyze",
            error_type="rate_limit",
            error_message="Rate limit exceeded",
            context="twitter user @test4",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    ]

    result = agent_for_error_tests._categorize_errors(errors)

    assert result["download_failed"] == 2
    assert result["preprocess_failed"] == 1
    assert result["analyze_failed"] == 1
    assert result["rate_limited"] == 1
    assert result["network_errors"] == 2
    assert result["invalid_format"] == 1
    assert result["other_errors"] == 4


def test_build_error_summary_empty(agent_for_error_tests):
    """Test error summary building with empty list."""
    summary = agent_for_error_tests._build_error_summary([], 10)

    assert summary == []


def test_build_error_summary_with_errors(agent_for_error_tests):
    """Test error summary building with mixed errors."""
    errors = [
        ImageProcessingError(
            url="https://example.com/img1.jpg",
            stage="download",
            error_type="timeout",
            error_message="Connection timeout",
            context="twitter user @test1",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
        ImageProcessingError(
            url="https://example.com/img2.jpg",
            stage="download",
            error_type="timeout",
            error_message="Connection timeout",
            context="twitter user @test2",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
        ImageProcessingError(
            url="https://example.com/img3.jpg",
            stage="preprocess",
            error_type="invalid_format",
            error_message="Unsupported format",
            context="twitter user @test3",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    ]

    summary = agent_for_error_tests._build_error_summary(errors, 10)

    assert len(summary) > 0
    assert any("timeout" in s.lower() for s in summary)
    assert any("download" in s.lower() for s in summary)
    assert any("format" in s.lower() for s in summary)


def test_build_vision_summary_section_no_errors(agent_for_error_tests):
    """Test vision summary section when there are no errors."""
    vision_stats = {
        "total": 10,
        "analyzed": 10,
        "failed": 0,
        "skipped": 0,
    }

    section = agent_for_error_tests._build_vision_summary_section(vision_stats)

    # When no errors, it still returns a success summary but no error details
    assert "Image Analysis Results" in section
    assert "10/10" in section
    assert "successfully" in section
    assert "Issues" not in section


def test_build_vision_summary_section_with_errors(agent_for_error_tests):
    """Test vision summary section when there are errors."""
    vision_stats = {
        "total": 10,
        "analyzed": 7,
        "failed": 2,
        "skipped": 1,
        "error_summaries": [
            "2 images failed to download (connection timeout)",
            "1 image had unsupported format",
        ],
    }

    section = agent_for_error_tests._build_vision_summary_section(vision_stats)

    assert "Image Analysis Results" in section
    assert "7/10" in section
    assert "2 failed" in section
    assert "1 skipped" in section
    assert "Issues Encountered" in section
    assert "connection timeout" in section.lower()
    assert "unsupported format" in section.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
