"""
Tests for socialosintagent/api_models.py — Pydantic request/response validation.

Covers:
- SessionCreateRequest: valid creation, empty platforms, empty usernames, name length
- SessionRenameRequest: valid rename, name length constraints
- SessionUpdateTargetsRequest: valid update, empty platforms
- AnalysisRequest: valid query, empty query, length cap, force_refresh default
- PurgeRequest: valid targets, invalid targets, keys field
- JobStatusResponse: full construction, optional fields
- PlatformInfo / PlatformsResponse: construction
- DiscoveredContactItem / ContactsResponse: construction and defaults
- DismissContactRequest: valid, empty platform/username
- ErrorResponse: construction
"""

import pytest
from pydantic import ValidationError

from socialosintagent.api_models import (
    AnalysisRequest,
    CacheStatusResponse,
    ContactsResponse,
    DiscoveredContactItem,
    DismissContactRequest,
    ErrorResponse,
    JobStatusResponse,
    PlatformInfo,
    PlatformsResponse,
    PurgeRequest,
    SessionCreateRequest,
    SessionRenameRequest,
    SessionUpdateTargetsRequest,
)


class TestSessionCreateRequest:
    def test_valid_minimal(self):
        req = SessionCreateRequest(name="Test", platforms={"twitter": ["alice"]})
        assert req.name == "Test"
        assert req.platforms == {"twitter": ["alice"]}
        assert req.fetch_options is None

    def test_valid_with_fetch_options(self):
        req = SessionCreateRequest(
            name="With Opts",
            platforms={"github": ["bob"]},
            fetch_options={"default_count": 100},
        )
        assert req.fetch_options == {"default_count": 100}

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            SessionCreateRequest(name="", platforms={"twitter": ["a"]})

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError):
            SessionCreateRequest(name="x" * 101, platforms={"twitter": ["a"]})

    def test_name_max_length_accepted(self):
        req = SessionCreateRequest(name="x" * 100, platforms={"twitter": ["a"]})
        assert len(req.name) == 100

    def test_missing_platforms_rejected(self):
        with pytest.raises(ValidationError):
            SessionCreateRequest(name="No platforms")

    def test_empty_platforms_dict_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            SessionCreateRequest(name="Empty", platforms={})
        assert "at least one entry" in str(exc_info.value)

    def test_platform_with_empty_usernames_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            SessionCreateRequest(name="Bad", platforms={"twitter": []})
        assert "no usernames" in str(exc_info.value)

    def test_multi_platform_accepted(self):
        req = SessionCreateRequest(
            name="Multi",
            platforms={"twitter": ["alice"], "github": ["bob"], "reddit": ["charlie"]},
        )
        assert len(req.platforms) == 3


class TestSessionRenameRequest:
    def test_valid_rename(self):
        req = SessionRenameRequest(name="New Name")
        assert req.name == "New Name"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            SessionRenameRequest(name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError):
            SessionRenameRequest(name="y" * 101)


class TestSessionUpdateTargetsRequest:
    def test_valid_update(self):
        req = SessionUpdateTargetsRequest(platforms={"hackernews": ["pg"]})
        assert req.platforms == {"hackernews": ["pg"]}
        assert req.fetch_options is None

    def test_empty_platforms_rejected(self):
        with pytest.raises(ValidationError):
            SessionUpdateTargetsRequest(platforms={})

    def test_with_fetch_options(self):
        req = SessionUpdateTargetsRequest(
            platforms={"twitter": ["a"]}, fetch_options={"default_count": 20}
        )
        assert req.fetch_options == {"default_count": 20}


class TestAnalysisRequest:
    def test_valid_query(self):
        req = AnalysisRequest(query="Summarize this user's activity")
        assert req.query == "Summarize this user's activity"
        assert req.force_refresh is False

    def test_force_refresh_true(self):
        req = AnalysisRequest(query="test", force_refresh=True)
        assert req.force_refresh is True

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            AnalysisRequest(query="")

    def test_query_max_length_accepted(self):
        req = AnalysisRequest(query="x" * 500)
        assert len(req.query) == 500

    def test_query_too_long_rejected(self):
        with pytest.raises(ValidationError):
            AnalysisRequest(query="x" * 501)


class TestJobStatusResponse:
    def test_full_construction(self):
        resp = JobStatusResponse(
            job_id="j1",
            session_id="s1",
            status="complete",
            query="test",
            query_id="q1",
            error=None,
            progress={"step": "done"},
        )
        assert resp.job_id == "j1"
        assert resp.status == "complete"
        assert resp.query_id == "q1"
        assert resp.progress == {"step": "done"}

    def test_minimal_construction(self):
        resp = JobStatusResponse(
            job_id="j1", session_id="s1", status="running", query="q"
        )
        assert resp.query_id is None
        assert resp.error is None
        assert resp.progress is None


class TestCacheStatusResponse:
    def test_empty(self):
        resp = CacheStatusResponse(entries=[])
        assert resp.entries == []

    def test_with_entries(self):
        resp = CacheStatusResponse(
            entries=[{"platform": "twitter", "username": "alice"}]
        )
        assert len(resp.entries) == 1


class TestPurgeRequest:
    def test_valid_single_target(self):
        req = PurgeRequest(targets=["cache"])
        assert req.targets == ["cache"]
        assert req.keys is None

    def test_valid_multiple_targets(self):
        req = PurgeRequest(targets=["cache", "media"])
        assert len(req.targets) == 2

    def test_valid_all_target(self):
        req = PurgeRequest(targets=["all"])
        assert req.targets == ["all"]

    def test_valid_specific_target_with_keys(self):
        req = PurgeRequest(targets=["specific"], keys=["twitter_alice"])
        assert req.keys == ["twitter_alice"]

    def test_invalid_target_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            PurgeRequest(targets=["passwords"])
        assert "Invalid purge target" in str(exc_info.value)

    def test_mixed_valid_and_invalid_rejected(self):
        with pytest.raises(ValidationError):
            PurgeRequest(targets=["cache", "invalid"])


class TestPlatformInfo:
    def test_available_platform(self):
        info = PlatformInfo(name="twitter", available=True)
        assert info.available is True
        assert info.reason is None

    def test_unavailable_with_reason(self):
        info = PlatformInfo(
            name="reddit", available=False, reason="Missing credentials"
        )
        assert info.reason == "Missing credentials"


class TestPlatformsResponse:
    def test_construction(self):
        resp = PlatformsResponse(
            platforms=[
                PlatformInfo(name="twitter", available=True),
                PlatformInfo(name="reddit", available=False, reason="No token"),
            ]
        )
        assert len(resp.platforms) == 2


class TestDiscoveredContactItem:
    def test_minimal(self):
        item = DiscoveredContactItem(
            platform="twitter", username="bob", interaction_types=["mention"], weight=3
        )
        assert item.platform == "twitter"
        assert item.first_seen is None
        assert item.last_seen is None

    def test_with_timestamps(self):
        item = DiscoveredContactItem(
            platform="github",
            username="alice",
            interaction_types=["repo_interaction"],
            weight=1,
            first_seen="2024-01-01T00:00:00Z",
            last_seen="2024-06-01T00:00:00Z",
        )
        assert item.first_seen == "2024-01-01T00:00:00Z"


class TestContactsResponse:
    def test_empty(self):
        resp = ContactsResponse(contacts=[], dismissed=[], total_extracted=0)
        assert resp.contacts == []
        assert resp.total_extracted == 0

    def test_with_contacts(self):
        contact = DiscoveredContactItem(
            platform="twitter", username="bob", interaction_types=["mention"], weight=5
        )
        resp = ContactsResponse(
            contacts=[contact],
            dismissed=["reddit/spam"],
            total_extracted=2,
        )
        assert len(resp.contacts) == 1
        assert resp.dismissed == ["reddit/spam"]
        assert resp.total_extracted == 2


class TestDismissContactRequest:
    def test_valid(self):
        req = DismissContactRequest(platform="twitter", username="bob")
        assert req.platform == "twitter"
        assert req.username == "bob"

    def test_empty_platform_rejected(self):
        with pytest.raises(ValidationError):
            DismissContactRequest(platform="", username="bob")

    def test_empty_username_rejected(self):
        with pytest.raises(ValidationError):
            DismissContactRequest(platform="twitter", username="")


class TestErrorResponse:
    def test_with_detail(self):
        err = ErrorResponse(error="Not Found", detail="Session does not exist")
        assert err.error == "Not Found"
        assert err.detail == "Session does not exist"

    def test_without_detail(self):
        err = ErrorResponse(error="Internal Error")
        assert err.detail is None
