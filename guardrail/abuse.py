"""
Rate limiting and repeat-offender tracking, keyed by tenant_id (see
guardrail/policy.py). Deliberately in-memory and single-process — this
project is local-first, not a distributed service (see CLAUDE.md); state
resets on process restart. If multi-process/distributed deployment ever
becomes a real requirement, this is the seam to swap for Redis or similar,
not a reason to add that complexity now.

RateLimiter: sliding 60-second window, "allow at most N calls/minute".
OffenderTracker: counts UNSAFE decisions per tenant; escalates (further
requests blocked by api.py) once `threshold` UNSAFE decisions land inside
`window_seconds`.
"""
import time
from collections import defaultdict, deque


def _now() -> float:
    return time.monotonic()


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, tenant_id: str, limit_per_minute: int) -> bool:
        now = _now()
        window = self._hits[tenant_id]
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= limit_per_minute:
            return False
        window.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


class OffenderTracker:
    def __init__(self):
        self._events: dict[str, deque] = defaultdict(deque)

    def record_unsafe(self, tenant_id: str) -> None:
        self._events[tenant_id].append(_now())

    def is_escalated(self, tenant_id: str, threshold: int, window_seconds: int) -> bool:
        now = _now()
        events = self._events[tenant_id]
        cutoff = now - window_seconds
        while events and events[0] < cutoff:
            events.popleft()
        return len(events) >= threshold

    def reset(self) -> None:
        self._events.clear()


rate_limiter = RateLimiter()
offender_tracker = OffenderTracker()
