"""
Tests for socialosintagent/exceptions.py — custom exception hierarchy.

Covers:
- RateLimitExceededError: message, original_exception, inheritance
- UserNotFoundError: message, inheritance
- AccessForbiddenError: message, inheritance
- All exceptions are catchable as Exception
"""

import pytest

from socialosintagent.exceptions import (
    AccessForbiddenError,
    RateLimitExceededError,
    UserNotFoundError,
)


class TestRateLimitExceededError:
    def test_message_stored(self):
        err = RateLimitExceededError("Twitter rate limit hit")
        assert str(err) == "Twitter rate limit hit"

    def test_original_exception_stored(self):
        original = ValueError("original cause")
        err = RateLimitExceededError("rate limited", original_exception=original)
        assert err.original_exception is original

    def test_original_exception_defaults_to_none(self):
        err = RateLimitExceededError("rate limited")
        assert err.original_exception is None

    def test_is_exception(self):
        err = RateLimitExceededError("test")
        assert isinstance(err, Exception)

    def test_can_be_caught_as_exception(self):
        with pytest.raises(Exception):
            raise RateLimitExceededError("caught")

    def test_can_be_caught_specifically(self):
        with pytest.raises(RateLimitExceededError):
            raise RateLimitExceededError("caught specifically")


class TestUserNotFoundError:
    def test_message_stored(self):
        err = UserNotFoundError("user 'alice' not found")
        assert str(err) == "user 'alice' not found"

    def test_is_exception(self):
        assert isinstance(UserNotFoundError("x"), Exception)

    def test_can_be_caught_specifically(self):
        with pytest.raises(UserNotFoundError):
            raise UserNotFoundError("not found")

    def test_does_not_have_original_exception_attr(self):
        err = UserNotFoundError("test")
        assert not hasattr(err, "original_exception")


class TestAccessForbiddenError:
    def test_message_stored(self):
        err = AccessForbiddenError("private account")
        assert str(err) == "private account"

    def test_is_exception(self):
        assert isinstance(AccessForbiddenError("x"), Exception)

    def test_can_be_caught_specifically(self):
        with pytest.raises(AccessForbiddenError):
            raise AccessForbiddenError("forbidden")


class TestExceptionHierarchy:
    def test_distinct_types(self):
        assert RateLimitExceededError is not UserNotFoundError
        assert UserNotFoundError is not AccessForbiddenError
        assert RateLimitExceededError is not AccessForbiddenError

    def test_all_catchable_as_exception(self):
        exceptions = [
            RateLimitExceededError("r"),
            UserNotFoundError("u"),
            AccessForbiddenError("a"),
        ]
        for exc in exceptions:
            assert isinstance(exc, Exception)

    def test_rate_limit_preserves_chained_exception(self):
        original = ConnectionError("network down")
        err = RateLimitExceededError("rate limited", original_exception=original)
        assert err.original_exception is original
        assert isinstance(err.original_exception, ConnectionError)
