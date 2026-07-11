"""Shared fixtures: reset in-memory abuse-control state between tests so one
test's rate-limit/offender hits can't leak into the next."""
import pytest

from guardrail.abuse import offender_tracker, rate_limiter


@pytest.fixture(autouse=True)
def _reset_abuse_state():
    rate_limiter.reset()
    offender_tracker.reset()
    yield
    rate_limiter.reset()
    offender_tracker.reset()
