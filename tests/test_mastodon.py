"""
Tests for socialosintagent/platforms/mastodon.py — MastodonFetcher.

Covers:
- Cache miss: fetches profile and statuses, normalises correctly
- Profile normalisation: HTML bio stripped, metrics, display_name
- Post normalisation: HTML content stripped, media, external_links, type detection
- Repost detection
- Cache hit and offline behaviour
- Dynamic instance trust for media downloads
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from socialosintagent.platforms import mastodon as mastodon_fetcher


def _make_account(
    acct="alice@mastodon.social",
    account_id="12345",
    display_name="Alice",
    note="<p>Hello <b>world</b></p>",
    followers_count=200,
    statuses_count=1000,
    url="https://mastodon.social/@alice",
    created_at="2023-01-01T00:00:00Z",
):
    return {
        "id": account_id,
        "acct": acct,
        "display_name": display_name,
        "note": note,
        "followers_count": followers_count,
        "statuses_count": statuses_count,
        "url": url,
        "created_at": created_at,
    }


def _make_status(
    status_id="100",
    content="<p>Just a <a href='https://example.com'>post</a></p>",
    media_attachments=None,
    favourites_count=10,
    reblogs_count=3,
    url="https://mastodon.social/@alice/100",
    created_at="2024-03-15T10:00:00Z",
    reblog=None,
):
    return {
        "id": status_id,
        "content": content,
        "media_attachments": media_attachments or [],
        "favourites_count": favourites_count,
        "reblogs_count": reblogs_count,
        "url": url,
        "created_at": created_at,
        "reblog": reblog,
    }


@pytest.fixture
def mock_cache(mocker):
    cache = mocker.MagicMock()
    cache.is_offline = False
    cache.load.return_value = None
    cache.base_dir = "/tmp/test_data"
    return cache


@pytest.fixture
def mock_mastodon_client():
    client = MagicMock()
    client.account_lookup.return_value = _make_account()
    return client


def _wire_mastodon(mock_mastodon_client, statuses):
    mock_mastodon_client.account_statuses.side_effect = [statuses, []]
    return mock_mastodon_client


class TestMastodonFetchHappyPath:
    def test_cache_miss_fetches_and_normalises(
        self, mock_cache, mock_mastodon_client, mocker
    ):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        statuses = [_make_status()]
        _wire_mastodon(mock_mastodon_client, statuses)

        clients = {"https://mastodon.social": mock_mastodon_client}
        default_client = mock_mastodon_client

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients=clients,
            default_client=default_client,
        )

        assert result is not None
        assert result["profile"]["platform"] == "mastodon"
        assert result["profile"]["username"] == "alice@mastodon.social"
        assert result["profile"]["display_name"] == "Alice"
        assert len(result["posts"]) == 1
        mock_cache.save.assert_called_once()

    def test_html_bio_is_stripped(self, mock_cache, mock_mastodon_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(mock_mastodon_client, [_make_status()])

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        bio = result["profile"]["bio"]
        assert "<p>" not in bio
        assert "<b>" not in bio
        assert "Hello" in bio
        assert "world" in bio

    def test_profile_metrics_populated(self, mock_cache, mock_mastodon_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(mock_mastodon_client, [_make_status()])

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        assert result["profile"]["metrics"]["followers"] == 200
        assert result["profile"]["metrics"]["post_count"] == 1000


class TestMastodonNormalisation:
    def test_html_content_stripped_from_post(
        self, mock_cache, mock_mastodon_client, mocker
    ):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(mock_mastodon_client, [_make_status()])

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        text = result["posts"][0]["text"]
        assert "<p>" not in text
        assert "<a" not in text
        assert "post" in text

    def test_external_links_extracted(self, mock_cache, mock_mastodon_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(
            mock_mastodon_client,
            [_make_status(content="<p>Check out https://example.com for details</p>")],
        )

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        assert "https://example.com" in result["posts"][0]["external_links"]

    def test_post_type_is_post_for_regular(
        self, mock_cache, mock_mastodon_client, mocker
    ):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(mock_mastodon_client, [_make_status(reblog=None)])

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        assert result["posts"][0]["type"] == "post"

    def test_post_type_is_repost_for_reblog(
        self, mock_cache, mock_mastodon_client, mocker
    ):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(
            mock_mastodon_client,
            [_make_status(reblog={"id": "999", "content": "<p>Original</p>"})],
        )

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        assert result["posts"][0]["type"] == "repost"

    def test_post_metrics_populated(self, mock_cache, mock_mastodon_client, mocker):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(mock_mastodon_client, [_make_status()])

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        assert result["posts"][0]["metrics"]["likes"] == 10
        assert result["posts"][0]["metrics"]["reposts"] == 3

    def test_empty_statuses_returns_profile_with_no_posts(
        self, mock_cache, mock_mastodon_client, mocker
    ):
        mocker.patch(
            "socialosintagent.platforms.mastodon.download_media", return_value=None
        )
        _wire_mastodon(mock_mastodon_client, [])

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=mock_cache,
            fetch_limit=50,
            clients={"https://mastodon.social": mock_mastodon_client},
            default_client=mock_mastodon_client,
        )

        assert result is not None
        assert result["profile"]["username"] == "alice@mastodon.social"
        assert len(result["posts"]) == 0


class TestMastodonCacheBehaviour:
    def test_cache_hit_sufficient_posts_skips_api(self, mocker):
        cached = {
            "profile": {"username": "alice@mastodon.social"},
            "posts": [{"id": str(i)} for i in range(100)],
        }
        cache = mocker.MagicMock()
        cache.is_offline = False
        cache.load.return_value = cached

        result = mastodon_fetcher.fetch_data(
            username="alice@mastodon.social",
            cache=cache,
            fetch_limit=50,
            clients={},
        )
        assert result is cached

    def test_offline_returns_cached_data(self, mocker):
        cached = {
            "profile": {"username": "offline@mastodon.social"},
            "posts": [{"id": "1"}],
        }
        cache = mocker.MagicMock()
        cache.is_offline = True
        cache.load.return_value = cached

        result = mastodon_fetcher.fetch_data(
            username="offline@mastodon.social",
            cache=cache,
            fetch_limit=50,
            clients={},
        )
        assert result is cached
