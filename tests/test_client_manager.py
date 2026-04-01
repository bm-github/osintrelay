"""
Tests for socialosintagent/client_manager.py — ClientManager.

Covers:
- get_available_platforms: with/without credential checking, always-available platforms
- get_platform_client: dispatching to correct property, unknown platform returns None
- twitter_client: missing token raises RuntimeError
- reddit_client: missing credentials raises RuntimeError
- bluesky_client: missing credentials raises RuntimeError
- get_mastodon_clients: no env vars returns empty dict
"""

import pytest

from socialosintagent.client_manager import ClientManager


class TestGetAvailablePlatforms:
    def test_without_cred_check_returns_all(self):
        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=False)
        assert "twitter" in platforms
        assert "reddit" in platforms
        assert "bluesky" in platforms
        assert "mastodon" in platforms
        assert "github" in platforms
        assert "hackernews" in platforms

    def test_github_always_available(self, monkeypatch):
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "github" in platforms

    def test_hackernews_always_available(self, monkeypatch):
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "hackernews" in platforms

    def test_twitter_available_with_token(self, monkeypatch):
        monkeypatch.setenv("TWITTER_BEARER_TOKEN", "fake_token")
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "twitter" in platforms

    def test_twitter_not_available_without_token(self, monkeypatch):
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "twitter" not in platforms

    def test_reddit_available_with_all_creds(self, monkeypatch):
        monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "agent")
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "reddit" in platforms

    def test_reddit_not_available_with_partial_creds(self, monkeypatch):
        monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
        monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "reddit" not in platforms

    def test_bluesky_available_with_creds(self, monkeypatch):
        monkeypatch.setenv("BLUESKY_IDENTIFIER", "user.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_SECRET", "secret")
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "bluesky" in platforms

    def test_mastodon_available_with_instance_url(self, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_1_URL", "https://mastodon.social")
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert "mastodon" in platforms

    def test_returns_sorted_unique_list(self, monkeypatch):
        monkeypatch.setenv("TWITTER_BEARER_TOKEN", "t")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "r")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "rs")
        monkeypatch.setenv("REDDIT_USER_AGENT", "ra")
        monkeypatch.setenv("BLUESKY_IDENTIFIER", "b")
        monkeypatch.setenv("BLUESKY_APP_SECRET", "bs")
        monkeypatch.setenv("MASTODON_INSTANCE_1_URL", "https://m.test")

        cm = ClientManager(is_offline=True)
        platforms = cm.get_available_platforms(check_creds=True)
        assert platforms == sorted(platforms)


class TestGetPlatformClient:
    def test_github_returns_none(self, monkeypatch):
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        cm = ClientManager(is_offline=True)
        assert cm.get_platform_client("github") is None

    def test_unknown_platform_returns_none(self):
        cm = ClientManager(is_offline=True)
        assert cm.get_platform_client("instagram") is None

    def test_twitter_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        cm = ClientManager(is_offline=True)
        with pytest.raises(RuntimeError, match="Failed to initialize client"):
            cm.get_platform_client("twitter")

    def test_reddit_raises_without_creds(self, monkeypatch):
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        cm = ClientManager(is_offline=True)
        with pytest.raises(RuntimeError, match="Failed to initialize client"):
            cm.get_platform_client("reddit")

    def test_bluesky_raises_without_creds(self, monkeypatch):
        monkeypatch.delenv("BLUESKY_IDENTIFIER", raising=False)
        cm = ClientManager(is_offline=True)
        with pytest.raises(RuntimeError, match="Failed to initialize client"):
            cm.get_platform_client("bluesky")


class TestMastodonClients:
    def test_no_env_vars_returns_empty(self, monkeypatch):
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)
        cm = ClientManager(is_offline=True)
        clients, default = cm.get_mastodon_clients()
        assert clients == {}
        assert default is None

    def test_missing_token_skips_instance(self, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_1_URL", "https://mastodon.social")
        monkeypatch.delenv("MASTODON_INSTANCE_1_TOKEN", raising=False)
        cm = ClientManager(is_offline=True)
        clients, default = cm.get_mastodon_clients()
        assert clients == {}
        assert default is None

    def test_initialized_once_flag(self, monkeypatch):
        monkeypatch.delenv("MASTODON_INSTANCE_1_URL", raising=False)
        cm = ClientManager(is_offline=True)
        cm.get_mastodon_clients()
        assert cm._mastodon_clients_initialized is True
