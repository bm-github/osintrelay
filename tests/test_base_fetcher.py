"""
Tests for socialosintagent/platforms/base_fetcher.py — BaseFetcher and RateLimitHandler.

Covers:
- BaseFetcher.fetch_data: offline mode, cache hit with sufficient posts, cache miss with
  profile + batch fetching, force_refresh bypasses cache, deduplication of posts,
  error propagation through _handle_api_error
- BaseFetcher._handle_api_error: rate limit, not found, forbidden, generic re-raise
- RateLimitHandler.check_response_headers: remaining=0, retry-after header, clean headers
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from socialosintagent.platforms.base_fetcher import BaseFetcher, RateLimitHandler
from socialosintagent.exceptions import (
    AccessForbiddenError,
    RateLimitExceededError,
    UserNotFoundError,
)
from socialosintagent.utils import NormalizedProfile, NormalizedPost


def _make_profile(username="testuser", platform="test"):
    return NormalizedProfile(
        platform=platform,
        id="123",
        username=username,
        display_name="Test User",
        bio="bio",
        profile_url=f"https://{platform}.com/{username}",
        metrics={},
    )


def _make_post(post_id="p1", text="hello"):
    return NormalizedPost(
        platform="test",
        id=post_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        author_username="testuser",
        text=text,
        media=[],
        external_links=[],
        post_url="https://test.com/post/1",
        metrics={},
        type="post",
    )


class ConcreteFetcher(BaseFetcher):
    """Minimal concrete implementation for testing BaseFetcher logic."""

    def __init__(self):
        super().__init__("test")
        self._profile = _make_profile()
        self._batch_items = []
        self._normalized_items = []

    def set_profile(self, profile):
        self._profile = profile

    def set_batch(self, items):
        self._batch_items = items

    def set_normalized(self, items):
        self._normalized_items = items

    def _fetch_profile(self, username, **kwargs):
        return self._profile

    def _fetch_batch(self, username, profile, needed, state, **kwargs):
        if state == "done":
            return [], None
        return self._batch_items, "done" if self._batch_items else None

    def _normalize(self, item, profile, **kwargs):
        if self._normalized_items:
            return self._normalized_items.pop(0)
        return _make_post(post_id=item)


class TestBaseFetcherOfflineMode:
    def test_offline_returns_cached_data(self, mocker):
        cached = {"profile": {"username": "cached"}, "posts": []}
        cache = mocker.MagicMock()
        cache.is_offline = True
        cache.load.return_value = cached

        fetcher = ConcreteFetcher()
        result = fetcher.fetch_data("user", cache)
        assert result is cached

    def test_offline_returns_none_when_no_cache(self, mocker):
        cache = mocker.MagicMock()
        cache.is_offline = True
        cache.load.return_value = None

        fetcher = ConcreteFetcher()
        result = fetcher.fetch_data("user", cache)
        assert result is None


class TestBaseFetcherCacheHit:
    def test_cache_hit_with_sufficient_posts_skips_api(self, mocker):
        cached = {
            "profile": _make_profile(),
            "posts": [_make_post(post_id=str(i)) for i in range(100)],
        }
        cache = mocker.MagicMock()
        cache.is_offline = False
        cache.load.return_value = cached

        fetcher = ConcreteFetcher()
        result = fetcher.fetch_data("user", cache, fetch_limit=50)
        assert result is cached
        cache.save.assert_not_called()


class TestBaseFetcherCacheMiss:
    def test_fetches_profile_and_posts(self, mocker):
        cache = mocker.MagicMock()
        cache.is_offline = False
        cache.load.return_value = None

        profile = _make_profile()
        post = _make_post()

        fetcher = ConcreteFetcher()
        fetcher.set_profile(profile)
        fetcher.set_batch(["item1"])
        fetcher.set_normalized([post])

        result = fetcher.fetch_data("user", cache, fetch_limit=50)

        assert result is not None
        assert result["profile"]["username"] == "testuser"
        assert len(result["posts"]) == 1
        cache.save.assert_called_once()

    def test_empty_batch_returns_profile_with_no_posts(self, mocker):
        cache = mocker.MagicMock()
        cache.is_offline = False
        cache.load.return_value = None

        fetcher = ConcreteFetcher()
        fetcher.set_profile(_make_profile())
        fetcher.set_batch([])

        result = fetcher.fetch_data("user", cache, fetch_limit=50)

        assert result is not None
        assert result["profile"]["username"] == "testuser"
        assert len(result["posts"]) == 0


class TestBaseFetcherForceRefresh:
    def test_force_refresh_bypasses_cache(self, mocker):
        cached = {
            "profile": _make_profile(),
            "posts": [_make_post(post_id=str(i)) for i in range(100)],
        }
        cache = mocker.MagicMock()
        cache.is_offline = False
        cache.load.return_value = cached

        post = _make_post(post_id="fresh")
        fetcher = ConcreteFetcher()
        fetcher.set_profile(_make_profile())
        fetcher.set_batch(["item1"])
        fetcher.set_normalized([post])

        result = fetcher.fetch_data("user", cache, force_refresh=True, fetch_limit=50)

        assert result is not cached
        assert result["posts"][0]["id"] == "fresh"
        cache.save.assert_called_once()


class TestBaseFetcherDeduplication:
    def test_duplicate_post_ids_are_deduplicated(self, mocker):
        cache = mocker.MagicMock()
        cache.is_offline = False
        cache.load.return_value = None

        p1 = _make_post(post_id="dup1")
        p2 = _make_post(post_id="dup1")

        fetcher = ConcreteFetcher()
        fetcher.set_profile(_make_profile())
        fetcher.set_batch(["a", "b"])
        fetcher.set_normalized([p1, p2])

        result = fetcher.fetch_data("user", cache, fetch_limit=50)

        ids = [p["id"] for p in result["posts"]]
        assert ids.count("dup1") == 1


class TestHandleApiError:
    def test_rate_limit_string_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(RateLimitExceededError):
            fetcher._handle_api_error(Exception("rate limit exceeded"), "user")

    def test_too_many_requests_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(RateLimitExceededError):
            fetcher._handle_api_error(Exception("429 Too Many Requests"), "user")

    def test_not_found_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(UserNotFoundError):
            fetcher._handle_api_error(Exception("user not found"), "alice")

    def test_404_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(UserNotFoundError):
            fetcher._handle_api_error(Exception("404 Not Found"), "alice")

    def test_forbidden_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(AccessForbiddenError):
            fetcher._handle_api_error(Exception("Access forbidden"), "user")

    def test_403_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(AccessForbiddenError):
            fetcher._handle_api_error(Exception("403 Forbidden"), "user")

    def test_private_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(AccessForbiddenError):
            fetcher._handle_api_error(Exception("Account is private"), "user")

    def test_suspended_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(AccessForbiddenError):
            fetcher._handle_api_error(Exception("User suspended"), "user")

    def test_unknown_error_reraises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(ValueError):
            fetcher._handle_api_error(ValueError("something unexpected"), "user")

    def test_does_not_exist_raises(self):
        fetcher = ConcreteFetcher()
        with pytest.raises(UserNotFoundError):
            fetcher._handle_api_error(Exception("does not exist"), "user")


class TestRateLimitHandler:
    def test_remaining_zero_raises(self):
        with pytest.raises(RateLimitExceededError):
            RateLimitHandler.check_response_headers(
                {"x-ratelimit-remaining": "0"}, "test"
            )

    def test_remaining_nonzero_passes(self):
        RateLimitHandler.check_response_headers({"x-ratelimit-remaining": "50"}, "test")

    def test_retry_after_raises(self):
        with pytest.raises(RateLimitExceededError):
            RateLimitHandler.check_response_headers({"retry-after": "30"}, "test")

    def test_clean_headers_pass(self):
        RateLimitHandler.check_response_headers({}, "test")

    def test_non_digit_remaining_passes(self):
        RateLimitHandler.check_response_headers(
            {"x-ratelimit-remaining": "unlimited"}, "test"
        )
