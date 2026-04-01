"""
Tests for socialosintagent/platforms/bluesky.py — BlueskyFetcher.

Covers:
- Cache miss: fetches profile and feed, normalises correctly
- Profile normalisation: handle, display_name, bio, metrics
- Post normalisation: text, post_url, type detection (post vs reply)
- Cache hit with sufficient posts: skips API
- Offline mode: returns cached data
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from socialosintagent.platforms import bluesky as bluesky_fetcher


def _make_profile_response():
    profile = MagicMock()
    profile.did = "did:plc:abc123"
    profile.handle = "alice.bsky.social"
    profile.display_name = "Alice"
    profile.description = "Hello world"
    profile.followers_count = 100
    profile.posts_count = 500
    return profile


def _make_feed_post(
    uri="at://did:plc:abc123/app.bsky.feed.post/123",
    text="Hello from Bluesky",
    like_count=5,
    reply_count=2,
    has_reply=False,
    created_at="2024-01-15T12:00:00Z",
    author_did="did:plc:abc123",
    author_handle="alice.bsky.social",
):
    post = MagicMock()
    post.uri = uri
    post.like_count = like_count
    post.reply_count = reply_count
    post.author.did = author_did
    post.author.handle = author_handle
    post.embed = None

    record = MagicMock()
    record.text = text
    record.created_at = created_at
    record.reply = MagicMock() if has_reply else None
    post.record = record

    return post


def _make_feed_item(post=None):
    if post is None:
        post = _make_feed_post()
    item = MagicMock()
    item.post = post
    return item


@pytest.fixture
def mock_cache(mocker):
    cache = mocker.MagicMock()
    cache.is_offline = False
    cache.load.return_value = None
    cache.base_dir = "/tmp/test_data"
    return cache


@pytest.fixture
def mock_client(mocker):
    client = MagicMock()
    profile_resp = _make_profile_response()
    client.get_profile.return_value = profile_resp

    feed_item = _make_feed_item()
    feed_resp = MagicMock()
    feed_resp.feed = [feed_item]
    feed_resp.cursor = None
    client.get_author_feed.return_value = feed_resp

    client._session = MagicMock()
    client._session.access_jwt = "fake_jwt"

    return client


class TestBlueskyFetchHappyPath:
    def test_cache_miss_fetches_and_normalises(self, mock_cache, mock_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.bluesky.download_media", return_value=None
        )

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=mock_cache,
            fetch_limit=50,
            client=mock_client,
        )

        assert result is not None
        assert result["profile"]["platform"] == "bluesky"
        assert result["profile"]["username"] == "alice.bsky.social"
        assert result["profile"]["id"] == "did:plc:abc123"
        assert result["profile"]["display_name"] == "Alice"
        assert result["profile"]["bio"] == "Hello world"
        assert result["profile"]["metrics"]["followers"] == 100
        assert result["profile"]["metrics"]["posts"] == 500
        assert len(result["posts"]) == 1
        mock_cache.save.assert_called_once()

    def test_post_text_normalised(self, mock_cache, mock_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.bluesky.download_media", return_value=None
        )

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=mock_cache,
            fetch_limit=50,
            client=mock_client,
        )

        assert result["posts"][0]["text"] == "Hello from Bluesky"

    def test_post_url_constructed_correctly(self, mock_cache, mock_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.bluesky.download_media", return_value=None
        )

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=mock_cache,
            fetch_limit=50,
            client=mock_client,
        )

        assert "alice.bsky.social" in result["posts"][0]["post_url"]
        assert "123" in result["posts"][0]["post_url"]

    def test_post_type_is_post_for_regular(self, mock_cache, mock_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.bluesky.download_media", return_value=None
        )

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=mock_cache,
            fetch_limit=50,
            client=mock_client,
        )

        assert result["posts"][0]["type"] == "post"

    def test_post_type_is_reply_for_reply(self, mock_cache, mocker):
        client = MagicMock()
        client.get_profile.return_value = _make_profile_response()

        reply_post = _make_feed_post(has_reply=True)
        feed_item = _make_feed_item(post=reply_post)
        feed_resp = MagicMock()
        feed_resp.feed = [feed_item]
        feed_resp.cursor = None
        client.get_author_feed.return_value = feed_resp
        client._session = MagicMock()
        client._session.access_jwt = "fake_jwt"

        mocker.patch(
            "socialosintagent.platforms.bluesky.download_media", return_value=None
        )

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=mock_cache,
            fetch_limit=50,
            client=client,
        )

        assert result["posts"][0]["type"] == "reply"

    def test_post_metrics_populated(self, mock_cache, mock_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.bluesky.download_media", return_value=None
        )

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=mock_cache,
            fetch_limit=50,
            client=mock_client,
        )

        assert result["posts"][0]["metrics"]["likes"] == 5
        assert result["posts"][0]["metrics"]["replies"] == 2

    def test_empty_feed_returns_profile_with_no_posts(self, mock_cache, mocker):
        client = MagicMock()
        client.get_profile.return_value = _make_profile_response()
        feed_resp = MagicMock()
        feed_resp.feed = []
        feed_resp.cursor = None
        client.get_author_feed.return_value = feed_resp

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=mock_cache,
            fetch_limit=50,
            client=client,
        )

        assert result is not None
        assert result["profile"]["username"] == "alice.bsky.social"
        assert len(result["posts"]) == 0


class TestBlueskyCacheBehaviour:
    def test_cache_hit_sufficient_posts_skips_api(self, mocker):
        cached = {
            "profile": {"username": "alice.bsky.social"},
            "posts": [{"id": str(i)} for i in range(100)],
        }
        cache = mocker.MagicMock()
        cache.is_offline = False
        cache.load.return_value = cached

        result = bluesky_fetcher.fetch_data(
            username="alice.bsky.social",
            cache=cache,
            fetch_limit=50,
            client=MagicMock(),
        )
        assert result is cached

    def test_offline_returns_cached_data(self, mocker):
        cached = {
            "profile": {"username": "offline_user"},
            "posts": [{"id": "1"}],
        }
        cache = mocker.MagicMock()
        cache.is_offline = True
        cache.load.return_value = cached

        result = bluesky_fetcher.fetch_data(
            username="offline_user",
            cache=cache,
            fetch_limit=50,
            client=MagicMock(side_effect=AssertionError("No API in offline")),
        )
        assert result is cached
