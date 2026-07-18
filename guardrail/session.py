"""
Session-scoped multi-turn chat, layered on top of the stateless guardrail
core (screen_input()/process_prompt() in guardrail/__init__.py stay
unchanged and untouched — this module wraps them, it doesn't replace them).

WHY THIS EXISTS: a single-turn guardrail evaluates each prompt in isolation.
A long chat session is a documented attack surface the single-turn path
doesn't cover — jailbreaks that don't try to slip one bad prompt past the
classifier, but instead spend many turns eroding it (guilt, manufactured
urgency, false claims of prior consent, "it's just fiction" reframing —
see guardrail/manipulation.py) until a later prompt gets answered that
would have been blocked as message one. The design principle here is the
opposite of what those attacks rely on: a session gets STRICTER as it goes,
never more lenient. There is deliberately no mechanism anywhere in this
module that makes a session easier to get an UNSAFE-adjacent answer from
over time.

Two enforcement layers, both fail-closed:
  1. Per-turn: guardrail.manipulation.manipulation_check() runs on the new
     prompt AND on the prompt joined with recent session history (an
     escalation cue like "you already agreed" only exists across turns).
  2. Per-session circuit breaker: once a session accumulates
     SESSION_LOCK_THRESHOLD flagged turns (any UNSAFE decision — manipulation,
     injection, backstop, or classifier), the session is locked and every
     subsequent turn is rejected without even being screened. This is
     deliberate: a session that has already shown a repeated pattern of
     attempting to manipulate or jailbreak the guardrail should not get a
     fresh chance on every new phrasing.

Deliberately in-memory / single-process, same as guardrail/abuse.py — this
project is local-first (see CLAUDE.md); the seam to swap for a shared store
is the same one abuse.py already documents, not a reason to add it now.

TTL / EVICTION: SessionStore keeps every session it's ever seen unless
something evicts it, which is an unbounded-memory-growth risk for a
long-running api.py process. SESSION_TTL_SECONDS bounds this — a session
untouched for that long is treated as gone (a fresh ChatSession is created
on its next use, same as if it never existed; this deliberately does NOT
preserve flagged_count/locked state past the TTL). This is memory hygiene,
not a security boundary: session_id is client-supplied (api.py's
ChatRequest.session_id has no server-side identity check), so an attacker
can already get a "fresh" session at any time simply by sending a new id —
TTL eviction hands them nothing they couldn't already get for free. The
per-turn lockout in this module is therefore a soft, UX-level safeguard
against a *sustained* attempt on one session id, not a hard per-attacker
gate; the actual identity-keyed enforcement is guardrail/abuse.py's
tenant-scoped OffenderTracker (keyed by API key -> tenant_id, which a client
can't freely mint), and that tracker already has its own, independent
expiry window. Eviction here is lazy — swept on each get_or_create() call
rather than a background thread, so this stays a plain synchronous module
with no lifecycle to manage.
"""
import time
from collections import deque
from dataclasses import dataclass, field

from guardrail import Result, process_prompt, screen_input
from guardrail.manipulation import manipulation_check

SESSION_LOCK_THRESHOLD = 3  # flagged turns in a session before it's locked out entirely
MAX_HISTORY_TURNS = 6  # how many recent prompts are joined for cross-turn manipulation checks
SESSION_TTL_SECONDS = 3600  # a session idle this long is evicted (memory hygiene, not a security boundary)

_MSG_SESSION_LOCKED = "This session has been locked after repeated policy violations. Start a new session."


def _now() -> float:
    return time.monotonic()


@dataclass
class ChatSession:
    session_id: str
    turn_count: int = 0
    flagged_count: int = 0
    locked: bool = False
    history: deque = field(default_factory=lambda: deque(maxlen=MAX_HISTORY_TURNS))
    last_seen: float = field(default_factory=_now)


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}

    def _evict_expired(self) -> None:
        # api.py's /chat/message is a sync def, so FastAPI runs it in the
        # anyio threadpool -- concurrent requests can call this on separate
        # threads even under a single uvicorn worker. dict.pop(sid, None) is
        # idempotent, so a session already evicted by another thread doesn't
        # raise KeyError here (plain `del` would).
        cutoff = _now() - SESSION_TTL_SECONDS
        expired = [sid for sid, s in self._sessions.items() if s.last_seen < cutoff]
        for sid in expired:
            self._sessions.pop(sid, None)

    def get_or_create(self, session_id: str) -> ChatSession:
        self._evict_expired()
        if session_id not in self._sessions:
            self._sessions[session_id] = ChatSession(session_id=session_id)
        session = self._sessions[session_id]
        session.last_seen = _now()
        return session

    def active_count(self) -> int:
        """Number of non-expired sessions currently held (evicts first)."""
        self._evict_expired()
        return len(self._sessions)

    def reset(self) -> None:
        self._sessions.clear()


sessions = SessionStore()


def _locked_result() -> Result:
    return Result("UNSAFE", "session locked: repeated flagged turns", "", public_message=_MSG_SESSION_LOCKED)


def process_turn(session_id: str, prompt: str, no_model: bool = False) -> Result:
    """Screen one turn of a session. Never gets more lenient as turn_count
    grows — the circuit breaker below is the only session-level effect, and
    it only ever makes future turns stricter (a hard lock), never looser."""
    session = sessions.get_or_create(session_id)

    if session.locked:
        return _locked_result()

    session.turn_count += 1

    # cross-turn manipulation check: join recent history + this prompt so an
    # escalation cue spread across turns ("we've been through this" following
    # an earlier refused ask) is caught even if this single message looks benign.
    joined = " ".join(list(session.history) + [prompt])
    manip_this_turn = manipulation_check(prompt)
    manip_across_turns = manipulation_check(joined)
    session.history.append(prompt)

    if manip_this_turn.decision == "UNSAFE" or manip_across_turns.decision == "UNSAFE":
        session.flagged_count += 1
        if session.flagged_count >= SESSION_LOCK_THRESHOLD:
            session.locked = True
        reason = manip_this_turn.reason if manip_this_turn.decision == "UNSAFE" else manip_across_turns.reason
        return Result("UNSAFE", reason, "", public_message="This request was blocked by the input safety check.")

    result = screen_input(prompt) if no_model else process_prompt(prompt)

    if result.decision == "UNSAFE":
        session.flagged_count += 1
        if session.flagged_count >= SESSION_LOCK_THRESHOLD:
            session.locked = True

    return result
