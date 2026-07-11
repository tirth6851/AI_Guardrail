"""Unit tests for guardrail/abuse.py's rate limiter and offender tracker.
Uses fresh instances (not the module singletons) so window/threshold math
is tested in isolation; api.py-level integration is covered in test_api.py.
"""
from guardrail import abuse
from guardrail.abuse import OffenderTracker, RateLimiter


def test_rate_limiter_allows_up_to_limit():
    rl = RateLimiter()
    for _ in range(5):
        assert rl.allow("t1", limit_per_minute=5) is True
    assert rl.allow("t1", limit_per_minute=5) is False


def test_rate_limiter_is_per_tenant():
    rl = RateLimiter()
    for _ in range(3):
        rl.allow("t1", limit_per_minute=3)
    assert rl.allow("t1", limit_per_minute=3) is False
    assert rl.allow("t2", limit_per_minute=3) is True


def test_rate_limiter_window_expiry(monkeypatch):
    rl = RateLimiter()
    clock = {"t": 0.0}
    monkeypatch.setattr(abuse, "_now", lambda: clock["t"])
    for _ in range(3):
        assert rl.allow("t1", limit_per_minute=3) is True
    assert rl.allow("t1", limit_per_minute=3) is False
    clock["t"] += 61.0  # past the 60s sliding window
    assert rl.allow("t1", limit_per_minute=3) is True


def test_offender_tracker_escalates_after_threshold():
    ot = OffenderTracker()
    for _ in range(4):
        ot.record_unsafe("t1")
    assert ot.is_escalated("t1", threshold=5, window_seconds=3600) is False
    ot.record_unsafe("t1")
    assert ot.is_escalated("t1", threshold=5, window_seconds=3600) is True


def test_offender_tracker_is_per_tenant():
    ot = OffenderTracker()
    for _ in range(5):
        ot.record_unsafe("t1")
    assert ot.is_escalated("t1", threshold=5, window_seconds=3600) is True
    assert ot.is_escalated("t2", threshold=5, window_seconds=3600) is False


def test_offender_tracker_window_expiry(monkeypatch):
    ot = OffenderTracker()
    clock = {"t": 0.0}
    monkeypatch.setattr(abuse, "_now", lambda: clock["t"])
    for _ in range(5):
        ot.record_unsafe("t1")
    assert ot.is_escalated("t1", threshold=5, window_seconds=100) is True
    clock["t"] += 101.0  # past the offender window
    assert ot.is_escalated("t1", threshold=5, window_seconds=100) is False
