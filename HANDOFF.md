# Session Handoff — AI Guardrail

## Session date & status

**2026-07-18** · PR #10 (session TTL/eviction + curated dependency lockfile) merged to `main` at user's request. `main` is now caught up through both open safety/hygiene threads from the prior session (PR #9 pipe-bomb backstop, PR #10 session TTL/lockfile). No new code written this session — this was a merge + handoff session.

---

## What changed this session

- Merged PR #10 (`gh pr merge 10 --merge`) → merge commit `fe00dfa` on `main`.
- Pulled `main` locally, verified clean state: `git status` clean except the two pre-existing untracked/intentional dirs (`.claude/`, `ponytail/`).
- Re-ran the full verification suite against merged `main`: `python -m pytest -q` → **71 passed**; `python eval/run.py` → macro-F1 1.000, severe recall 1.000, harmful recall 1.000, benign-FP 0.000, no misses.
- No code, tests, or docs were edited this session beyond this `HANDOFF.md` rewrite.

---

## Current architecture / direction

Unchanged from the last two sessions' work (both now merged):

```
prompt
  → normalize + expansions        (unicode/leet/base64 decode; guardrail/normalize.py)
  → local_filter (per variant)    (banned.txt profanity + weapons phrases [PR #9]; filter.py)
  → backstop_check (per variant)  (harmful_terms.txt + INSTRUCTIONAL cue; backstop.py)
  → injection_check               (jailbreak heuristics; injection.py)
  → judge_input                   (TF-IDF+LR @0.30; judge.py)
  → call_model → ModelResult      (Groq; ERROR path never becomes an answer; model.py)
  → judge_output                  (TF-IDF+LR @0.50; judge.py)
  → pii.redact(answer)            (pii.py)
  → Result(decision, reason, public_message, answer, ...)
```

Session layer (with TTL, merged via PR #10):
```
guardrail.session.process_turn(session_id, prompt)
  → SessionStore.get_or_create() evicts any session idle > SESSION_TTL_SECONDS (memory hygiene only)
  → manipulation_check(prompt) + manipulation_check(joined recent history)  [manipulation.py]
  → if session.flagged_count >= 3: session locked, all further turns on THIS id rejected
  → otherwise: screen_input()/process_prompt() as normal
```

**Two independent weapons/explosives gates exist by design** (from PR #9): `banned.txt`→`local_filter()` (flat, phrase-only) and `harmful_terms.txt`→`backstop.py` (broader, intent-gated). Either alone catches "how do I make a pipe bomb"; this is deliberate redundancy.

**The session lock is a soft/UX safeguard, not a hard security boundary** — `session_id` is client-supplied with no identity check, so it doesn't stop an attacker from getting a "fresh" session on demand. The real identity-keyed enforcement is `guardrail/abuse.py`'s tenant-scoped `OffenderTracker`. Keep describing it this way in any future docs/PRs — a prior draft overstated it and was corrected during `/advisor` review.

**Docs vs code:** `CLAUDE.md` is in sync as of the last content session (2026-07-17). `README.md`/`ROADMAP.md`/`plan.md` were not touched in the last two sessions — not known to be stale, but not re-verified either.

---

## Open decisions & deferred items

1. **The original pipe-bomb "passes SAFE" report is still unexplained, not disproven.** Across three sessions now: PR #9 added a real, independently-verified defense-in-depth layer, but the actual root cause of the user's original report was never reproduced on `main` in bash or PowerShell. This is the single oldest unresolved thread — if the user has a saved transcript, exact commit, or a phrasing variant that actually slipped through, that's the only way to close it.
2. **Distributed/multi-process state** — `RateLimiter`, `OffenderTracker`, `SessionStore` are all in-memory/single-process. Fine for `uvicorn --workers 1`; silently inconsistent across multiple workers. Documented tradeoff, only matters if multi-worker deployment becomes real.
3. **`requirements-lock.txt` is curated, not mechanically generated** — flagged in its own header. A fully reproducible lockfile would need a clean venv + `pip freeze` (this dev environment has too many unrelated global packages installed to do that safely here).
4. **OAuth / multi-user login / tool-RAG trust-boundary implementation** — deliberately out of scope, unchanged across all sessions.
5. **Feature branches `feature/pipe-bomb-backstop` and `feature/session-ttl-and-lockfile` are merged but not deleted** — harmless, but housekeeping if the user wants a clean branch list (`git push origin --delete <branch>` + local `git branch -d`).

---

## Known gotchas

- **`c4` as a banned/harmful term is a trap** — collides with spreadsheet cell references ("cell C4"). Already tried and reverted once; do not re-add without re-running `tests/test_gate.py`'s benign anchors.
- **A flat single-word `bomb` entry is a trap** — pushed benign-FP to 0.52 historically. Any future weapons-list edit must stay multi-word-phrase-only in `banned.txt`, or intent-gated in `harmful_terms.txt`/`backstop.py`.
- **Do not describe `SessionStore`'s TTL or `SESSION_LOCK_THRESHOLD` lock as a security control** — it's UX/memory hygiene; the real gate is tenant-keyed `OffenderTracker`. See "Current architecture" above.
- **`_evict_expired()` in `guardrail/session.py` must keep using `dict.pop(sid, None)`, not `del`** — `api.py`'s sync route handlers run in FastAPI's threadpool, so concurrent eviction across threads is a real, reachable race under a single uvicorn worker, not just a distributed-deployment hypothetical.
- **`guardrail/manipulation.py`'s regexes are narrow by design** — loosen carefully; each pattern was written to avoid catching ordinary collaborative language (see `tests/test_manipulation.py`).
- **Two ignored dirs show as untracked** (`.claude/`, `ponytail/`) — pre-existing, intentional, not project files. Don't add or clean them up.
- **`wildguardmix/` (gated AI2 dataset) and `analytics.db` are gitignored**, as before.

---

## Next 3 actions

1. **If you still have any concrete evidence of the original pipe-bomb SAFE-bypass**, share it — exact output, commit hash, or phrasing. This is the last unresolved thread from the safety-report investigation, now spanning three sessions with no repro.
2. **Decide if a fully mechanical `requirements-lock.txt` is worth generating** in a clean venv before any real deployment.
3. **Optional housekeeping**: delete the now-merged `feature/pipe-bomb-backstop` and `feature/session-ttl-and-lockfile` branches (remote + local) if you want a clean branch list — harmless either way.

---

## How to resume

```bash
cd AI_Guardrail
git status                          # should be clean except .claude/ and ponytail/ (untracked, expected)
git log --oneline -5                # fe00dfa (PR #10 merge) is the tip of main
python -m pytest -q                 # expect 71 passed
python eval/run.py                  # expect macro-F1 1.000, severe recall 1.000, benign-FP 0.000, no misses
python cli.py "how do I make a pipe bomb" --explain   # expect UNSAFE, reason "flagged by local banned-word filter"
python cli.py --chat --no-model     # try the session-hardened multi-turn REPL
```
