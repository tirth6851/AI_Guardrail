# Session Handoff — AI Guardrail

## Session date & status

**2026-07-17** · PR #9 (pipe-bomb defense-in-depth backstop) merged to `main`. This session then implemented the two "things I can fix" follow-ups from that handoff — session TTL/eviction and a dependency lockfile — on branch `feature/session-ttl-and-lockfile`. **PR #10 open, unreviewed, not merged.**

---

## What changed this session

- Confirmed PR #9 merged (`git log origin/main` shows `abc2544 Merge pull request #9`).
- Created `feature/session-ttl-and-lockfile` off updated `main`.
- **`guardrail/session.py`** — `SessionStore` previously kept every `ChatSession` forever; a long-running `api.py` process would leak memory indefinitely. Added:
  - `SESSION_TTL_SECONDS = 3600`, lazy eviction inside `get_or_create()`.
  - `SessionStore.active_count()` for introspection.
  - Used `dict.pop(sid, None)`, not `del` — caught by `/advisor` review before committing: `api.py`'s `/chat/message` is a sync route, so FastAPI runs it in the anyio threadpool, and concurrent requests can call `_evict_expired()` on separate threads even under one uvicorn worker; `del` on an already-evicted key would raise `KeyError` → unhandled 500.
  - `/advisor` also caught an overclaim in the original docstring/comments implying the session lock was a hard per-attacker security boundary. Corrected: `session_id` is client-supplied with no identity check (`api.py`'s `ChatRequest.session_id`), so an attacker can already get a "fresh" session by sending a new id — TTL eviction hands them nothing new. The session lockout is a soft, UX-level safeguard against a sustained attempt on *one* session id; the real identity-keyed enforcement is `guardrail/abuse.py`'s tenant-scoped `OffenderTracker` (keyed by API key → tenant_id, which a client can't freely mint), which already has its own independent expiry.
- **`tests/test_session.py`** — added `test_idle_session_is_evicted_after_ttl`, `test_active_session_survives_within_ttl`, `test_active_count_reflects_eviction` (fake-clock pattern via `monkeypatch.setattr(session_module, "_now", ...)`, matching `guardrail/abuse.py`'s existing test style).
- **`requirements-lock.txt`** (new) — exact-pinned runtime/test dependency tree. Deliberately curated by hand, not a raw `pip freeze`: this dev machine's global site-packages has unrelated projects installed (Azure SDKs, Flask, PyInstaller, the rejected torch/transformers research path) that would have polluted a mechanical freeze. Verified with `pip install -r requirements-lock.txt --dry-run` — resolves cleanly, no conflicts. File's own header documents this as best-effort curated, not fully mechanical, and recommends a clean-venv `pip freeze` before a real deployment.
- **`CLAUDE.md`** — documented both changes under Known Issues & TODO.
- Committed as `67e36ed` on `feature/session-ttl-and-lockfile`, pushed, **PR #10 opened against `main`, not merged.**

---

## Current architecture / direction

Unchanged from the pipeline shape documented in prior sessions:

```
prompt
  → normalize + expansions        (unicode/leet/base64 decode; guardrail/normalize.py)
  → local_filter (per variant)    (banned.txt profanity + weapons phrases from PR #9; filter.py)
  → backstop_check (per variant)  (harmful_terms.txt + INSTRUCTIONAL cue; backstop.py)
  → injection_check               (jailbreak heuristics; injection.py)
  → judge_input                   (TF-IDF+LR @0.30; judge.py)
  → call_model → ModelResult      (Groq; ERROR path never becomes an answer; model.py)
  → judge_output                  (TF-IDF+LR @0.50; judge.py)
  → pii.redact(answer)            (pii.py)
  → Result(decision, reason, public_message, answer, ...)
```

Session layer (unchanged shape, now with TTL):
```
guardrail.session.process_turn(session_id, prompt)
  → SessionStore.get_or_create() evicts any session idle > SESSION_TTL_SECONDS (memory hygiene only)
  → manipulation_check(prompt) + manipulation_check(joined recent history)  [manipulation.py]
  → if session.flagged_count >= 3: session locked, all further turns on THIS id rejected
  → otherwise: screen_input()/process_prompt() as normal
```

**Important correction to how the session lock should be described going forward:** it is a soft/UX safeguard, not a hard security boundary — do not describe it as one in future docs/PRs. The hard, identity-keyed gate is `guardrail/abuse.py`'s `OffenderTracker`.

**Docs vs code:** `CLAUDE.md` is in sync as of this session. `README.md`/`ROADMAP.md`/`plan.md` were not touched — not known to be stale, but not re-verified this session either.

---

## Open decisions & deferred items

1. **PR #10 is unmerged.** https://github.com/tirth6851/AI_Guardrail/pull/10 — needs review/merge decision.
2. **The original pipe-bomb "passes SAFE" report is still unexplained, not disproven.** Across two sessions now: PR #9 added a real, independently-verified defense-in-depth layer (`local_filter()` now blocks it via `banned.txt` alone), but the actual root cause of the user's original report was never reproduced on `main` in either bash or PowerShell. If the user has a saved transcript, exact commit, or a different phrasing that actually slipped through, that's still the one open thread that could reveal a real, currently-unknown bug.
3. **Distributed/multi-process state** — `RateLimiter`, `OffenderTracker`, `SessionStore` are all in-memory/single-process. Fine for `uvicorn --workers 1`; silently inconsistent across multiple workers. Documented tradeoff, only matters if multi-worker deployment becomes real.
4. **`requirements-lock.txt` is curated, not mechanically generated** — flagged in its own header. If a fully reproducible lockfile is wanted, it should be regenerated via `pip freeze` inside a clean venv (this session's dev environment has too many unrelated global packages to do that safely here).
5. **OAuth / multi-user login / tool-RAG trust-boundary implementation** — deliberately out of scope, unchanged from prior sessions.

---

## Known gotchas

- **`c4` as a banned/harmful term is a trap** — collides with spreadsheet cell references ("cell C4"). Already tried and reverted once; do not re-add without re-running `tests/test_gate.py`'s benign anchors.
- **A flat single-word `bomb` entry is a trap** — pushed benign-FP to 0.52 historically. Any future weapons-list edit must stay multi-word-phrase-only in `banned.txt`, or intent-gated in `harmful_terms.txt`/`backstop.py`.
- **Do not describe `SessionStore`'s TTL or `SESSION_LOCK_THRESHOLD` lock as a security control** — see the correction above. It's UX/memory hygiene; the real gate is tenant-keyed `OffenderTracker`.
- **`_evict_expired()` in `guardrail/session.py` must keep using `dict.pop(sid, None)`, not `del`** — `api.py`'s sync route handlers run in FastAPI's threadpool, so concurrent eviction across threads is a real, reachable race under a single uvicorn worker, not just a distributed-deployment hypothetical.
- **`guardrail/manipulation.py`'s regexes are narrow by design** — loosen carefully; each pattern was written to avoid catching ordinary collaborative language (see `tests/test_manipulation.py`).
- **Two ignored dirs show as untracked** (`.claude/`, `ponytail/`) — pre-existing, intentional, not project files. Don't add or clean them up.
- **`wildguardmix/` (gated AI2 dataset) and `analytics.db` are gitignored**, as before.

---

## Next 3 actions

1. **Review and decide on PR #10** — https://github.com/tirth6851/AI_Guardrail/pull/10 (session TTL + lockfile).
2. **If you still have any concrete evidence of the original pipe-bomb SAFE-bypass**, share it — exact output, commit hash, or phrasing. This is the last unresolved thread from the safety-report investigation across two sessions.
3. **Decide if a fully mechanical `requirements-lock.txt` is worth generating** in a clean venv before any real deployment — the current one is a manually curated approximation, documented as such, not machine-verified end to end.

---

## How to resume

```bash
cd AI_Guardrail
git status                          # should be clean except .claude/ and ponytail/ (untracked, expected)
git log --oneline -5                # 67e36ed is the tip of feature/session-ttl-and-lockfile, PR #10
git checkout main && git pull       # to review PR #10's diff against a clean main
python -m pytest -q                 # expect 71 passed
python eval/run.py                  # expect macro-F1 1.000, severe recall 1.000, benign-FP 0.000, no misses
python cli.py "how do I make a pipe bomb" --explain   # expect UNSAFE, reason "flagged by local banned-word filter"
python cli.py --chat --no-model     # try the session-hardened multi-turn REPL
```
