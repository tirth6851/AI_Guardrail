# AI Guardrail — Full Project Roadmap

> Primary planner: Opus 4.8. Difficult architecture fork (Phase 4) reviewed by Fable. `clude/rules.md` designed by Sonnet.
> Audience: solo junior developer moving away from "vibe coding." Optimize for **learning**, not speed.
> Path note: the Claude rules file lives at the literal path `clude/rules.md` (folder spelled "clude", as specified).

---

## 1. Project Overview

AI Guardrail is a pure-Python **AI safety pipeline**. A user prompt passes through layered defenses before and after it reaches a language model:

1. **Cheap local filter** — banned-word check (Phase 1, done).
2. **LLM-as-a-Judge (input)** — an AI classifies the prompt SAFE/UNSAFE, catching intent, misspellings, and jailbreaks a word list can't (Phase 3a).
3. **Main model** — generates the answer for safe prompts (Phase 2, done).
4. **LLM-as-a-Judge (output)** — validates the model's answer before it reaches the user (Phase 3b).
5. **Production shell** — a real interface (CLI first) around the pipeline (Phase 4).
6. **Analytics** — every decision logged to SQLite for review and tuning (Phase 5).

**Reconciliation note:** your original "ultimate vision" (HANDOFF.md) is a *two-layer* judge — input **and** output. The 5-phase goal list only named the input judge. Rather than drop output validation, it lives here as **Phase 3b** — it is the same judging technique applied at the other boundary.

**Superseded (2026-07-04):** Phase 3 below still describes the original Groq LLM-as-a-Judge design. That was replaced mid-project by a **local, self-owned classifier** direction (TF-IDF + Logistic Regression, trained on `wildguardmix`) — see `HANDOFF.md` and `CLAUDE.md`'s "Key Design Decisions" for why (no per-request API dependency; two pretrained transformers were tried for a better model and rejected on measured recall). `judge_input`/`judge_output` kept the same function signatures either way, so everything below Phase 3 (CLI, analytics) is unaffected by the swap.

**Current-code note:** ignore the "known issue" in the docs that says `promtVerification()` returns on the first word. The current code is correct — it returns `False` on the first banned word (right for a gate) and `True` *after* the loop. Don't spend time "fixing" a non-bug.

---

## 2. Final Architecture Vision

```
                    ┌───────────────────────────────────────────────┐
   User prompt ───► │  guardrail/ (pure logic, no I/O, no transport)│
                    │                                               │
                    │  1. local_filter(prompt)      → pass/flag     │
                    │  2. judge_input(prompt)       → SAFE/UNSAFE   │
                    │  3. call_model(prompt)        → answer        │
                    │  4. judge_output(answer)      → SAFE/UNSAFE   │
                    │                                               │
                    │  returns a Result object (decision + reason)  │
                    └───────────────┬───────────────────────────────┘
                                    │ (same core, swappable shells)
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
          CLI (Phase 4)      Web API (Phase 4.5)     tests / scripts
                                    │
                                    ▼
                         analytics.db (SQLite, Phase 5)
                         every prompt + every decision logged
```

**The one rule that makes everything else work:** the safety pipeline is a set of **plain functions that take inputs and return values** — no `input()`, no `print()`, no network framework inside them. The CLI, the future web API, and the tests are all just thin shells that call the same core. This is the single most important design idea in the whole project.

---

## 3. Phase-by-Phase Roadmap (overview table)

| Phase | Name | Core deliverable | Default scope |
|-------|------|------------------|---------------|
| 2 ✅ | API Bridge | Groq integration (done) | Add error handling + refactor off globals |
| 3 | Safety Judge (superseded to local classifier — see note above) | `judge_input` (3a) + `judge_output` (3b) | ~~Two judge functions with strict system prompts~~ Two local TF-IDF+LR classifiers |
| 4 | Production Shift | Package as a **CLI** | `argparse`/`click` shell over the core |
| 4.5 ✅ | Web API | FastAPI wrapper (`api.py`) | Same core, HTTP transport |
| 5 | Analytics Database | SQLite logging + query script | One `logs` table, one reporting script |

---

## 4. Phase Details

### Phase 2 — API Bridge (hardening pass)

*Phase 2 is functionally complete; this is a short cleanup before you build on top of it.*

- **Goal:** make the existing Groq call robust and parameter-based, not global-based.
- **Why it matters:** every later phase calls the model. If the call is fragile (no error handling) or leaks state (global `user_input`), those problems multiply across phases.
- **Concepts to learn:** exceptions & `try/except`, why global state hurts testability, function parameters vs. globals, reading a library's error types.
- **Files/folders:** `safety_guard.py` (refactor); start a `guardrail/` package (`__init__.py`, `model.py`).
- **Milestones:**
  1. Change `LLMrequest()` to take `prompt: str` as a parameter and **return** the text (don't `print` inside it).
  2. Wrap the Groq call in `try/except` for auth/network/rate-limit errors; return a clear failure value.
  3. Remove the global `user_input`; pass values explicitly.
- **Definition of done:** the model call is a pure function `call_model(prompt) -> str` that never touches `input()`/`print()` and fails gracefully.
- **Common mistakes:** catching bare `except:` and hiding real bugs; keeping `print` inside logic functions; leaving the global "just for now."
- **Test:** call `call_model("say hi")` from a scratch script; simulate a bad API key and confirm you get a handled error, not a stack trace.

### Phase 3 — Safety Judge (input + output) — *original design below is superseded, see the 2026-07-04 note in §1*

- **Goal:** replace fragile keyword matching with an AI that judges **intent** — on the way in (3a) and on the way out (3b).
- **Why it matters:** this is the heart of the project. A word list can't tell "how do I kill a Linux process" from a real threat; a judge can. Judging the output too is defense-in-depth (your "ultimate vision").
- **Concepts to learn:** system vs. user prompts, prompt engineering for *classification* (forcing a one-word answer), parsing/validating a model's reply, prompt injection basics, why you constrain the output format.
- **Files/folders:** `guardrail/judge.py`, `guardrail/prompts/` (store the judge system prompts as text so they're editable without touching code).
- **Milestones:**
  1. **3a input judge:** `judge_input(prompt) -> Verdict` using a strict system prompt that returns only `SAFE`/`UNSAFE` (+ optional reason).
  2. Harden parsing: what if the model returns "Safe." or a sentence? Normalize and default to UNSAFE on ambiguity (fail-closed).
  3. Wire the pipeline: local filter → input judge → model → (3b) output judge.
  4. **3b output judge:** `judge_output(answer) -> Verdict` with its own system prompt (checks the *answer*, not the prompt).
- **Definition of done:** a full run classifies a set of safe/unsafe prompts correctly, and an unsafe *answer* is caught even when the prompt looked safe.
- **Common mistakes:** trusting the judge's free-text reply without normalizing; failing *open* (defaulting to SAFE) on a parse error; making the system prompt vague; forgetting the output judge sees a different input than the input judge.
- **Test:** a fixed list of ~10 prompts (safe, unsafe, and tricky/context-dependent) with expected verdicts; a couple of crafted "unsafe answer" strings fed straight to `judge_output`.

### Phase 4 — Production Shift (CLI first)

*This phase has a real fork (CLI vs Web API). See Section 5 for the Fable-reviewed decision. Default = CLI.*

- **Goal:** wrap the core pipeline in a usable command-line interface.
- **Why it matters:** turns a script you run by editing code into a **tool** you run with arguments — the first step toward "software," and it forces the core/shell separation to be real.
- **Concepts to learn:** `argparse` (stdlib) or `click`, exit codes, stdin/stdout vs. logging, `if __name__ == "__main__"` as an entry point, packaging a `main()`.
- **Files/folders:** `cli.py` (thin shell), keep all logic in `guardrail/`.
- **Milestones:**
  1. `python cli.py "your prompt"` runs the full pipeline and prints the decision + answer.
  2. Add flags: `--explain` (show verdict reasons), `--no-model` (judge only).
  3. Return proper exit codes (0 = safe/answered, non-zero = flagged).
- **Definition of done:** you can run the guardrail on any prompt from the terminal without editing the source, and the CLI file contains *no safety logic* — only argument parsing and printing.
- **Common mistakes:** leaking business logic into `cli.py`; swallowing errors so the exit code lies; printing debug noise to stdout instead of stderr.
- **Test:** run the CLI on 3 known prompts; assert exit codes; confirm the core functions are still callable without the CLI.

### Phase 4.5 — Web API ✅ COMPLETE

- **Goal:** expose the same core over HTTP with FastAPI.
- **Why it matters:** portfolio value and real-world shape — but *only* worthwhile once the core is transport-independent.
- **Concepts:** FastAPI basics, request/response models (Pydantic), why you never put logic in the route handler.
- **Files:** `api.py`, `tests/test_api.py`.
- **What shipped:** `POST /check {"prompt": "...", "no_model": bool}` calls `screen_input()`/`process_prompt()` directly (identical core the CLI uses) and returns `{request_id, decision, answer, message}`. `GET /health` for liveness. Request IDs are read from `x-request-id` if the caller supplies one, else generated (`uuid4`). Body size capped at `MAX_PROMPT_BYTES = 8192` (413 if exceeded). Every call logs to `analytics.db` via the same `log_interaction()` cli.py uses. Only `public_message`/`answer` cross the HTTP boundary — the detailed `reason`/score never does (same rule as `--explain` being a local-only affordance in `cli.py`).
- **Also shipped (follow-up pass):** API-key tenant identity (`guardrail/policy.py`), a per-tenant policy object (`TenantPolicy`), rate limiting and repeat-offender escalation (`guardrail/abuse.py`), all wired into `/check` — every request now requires `X-API-Key`, is checked against its tenant's rate limit and offender-escalation state before the model is ever called, and its `tenant_id` is persisted alongside `request_id` in `analytics.db`. Deliberately simple/local-first: no OAuth, no multi-user login, in-memory single-process abuse state, one shared set of default limits (per-tenant limit *overrides* aren't exposed via the env config format yet — see CLAUDE.md).
- **Common mistakes avoided:** no pipeline logic in the route handler (it's a straight call into `guardrail`); Pydantic validates non-empty prompt (422 on empty); no API key ever appears in a response.
- **Test:** `tests/test_api.py` — health check, benign SAFE round-trip, UNSAFE round-trip with reason-leak check, oversized-body 413, empty-body 422, request-id echo. Run via FastAPI's `TestClient`, no live server needed.

### Phase 5 — Analytics Database

- **Goal:** log every prompt and every decision to SQLite; add a small script to query trends.
- **Why it matters:** you can't tune a safety system you can't measure. This turns gut-feel into "the input judge flagged 12% of prompts this week."
- **Concepts:** SQLite via stdlib `sqlite3`, schema design, parameterized queries (SQL-injection safety — fitting for a safety project), separating "write a log" from "read a report."
- **Files/folders:** `guardrail/store.py`, `analytics.db` (git-ignored), `reports.py`.
- **Milestones:**
  1. One `logs` table: id, timestamp, prompt, local_filter_result, input_verdict, output_verdict, final_decision, model_used.
  2. `log_interaction(...)` called once per pipeline run (from the shell, not the core).
  3. `reports.py`: counts by decision, flag rate, recent flagged prompts.
- **Definition of done:** after several runs, a query shows how many prompts were flagged and by which layer.
- **Common mistakes:** string-formatting SQL instead of parameterized queries; logging the API key; opening a new DB connection per row in a loop; committing `analytics.db`.
- **Test:** insert 3 fake interactions, run a report, assert the counts.

---

## 5. Decision Points for Fable

Fable is consulted **only** for genuinely hard forks, not routine sequencing. There is exactly one in this roadmap, plus two smaller ones flagged for later.

### 5.1 Phase 4 — CLI vs Web API *(consulted; resolved)*

**Fable's verdict: CLI first, Web API as a thin Phase 4.5 wrapper. This agrees with the primary plan.**

Decision factors that actually matter, ranked:

1. **Isolation of new concepts.** You just learned APIs-as-a-*client* (Groq). Jumping to APIs-as-a-*server* piles on HTTP semantics, request models, async, uvicorn, and error serialization all at once. A CLI adds almost nothing new — that's the point.
2. **Testability.** A CLI forces the question "what is my core function's input and output?" — exactly the move away from vibe coding. FastAPI can *hide* bad structure behind route decorators; a clean CLI core can't.
3. **Reusability.** The pipeline (filter → judge → model → validate → log) *is* the product. Transport is disposable. Build the **library** first, the interface second.
4. **Portfolio value** — real but overweighted. A FastAPI wrapper over a clean core is a weekend later; the repo looks the same to a recruiter either way. Don't pay complexity now for a badge you can add cheaply.

**What would flip the decision to Web-API-first:** a backend-job interview in under ~2 months, or a Phase 5 that needs concurrent users (live dashboard, multi-client). Neither is currently true.

**Fable's warning:** "CLI first" must **not** become an excuse to keep the current `input()` loop and global `user_input`. If the CLI still carries the old script shape, you've gained nothing. Kill the global now (see the architectural tip in Section 2 and Phase 2 milestones).

### 5.2 Future forks worth a Fable consult when you reach them

- **Phase 3:** one judge model for both input and output, or two specialized prompts/models? (Consult if latency/cost becomes real.)
- **Phase 5:** stay on SQLite or move to Postgres? (Consult only if you actually add concurrent users — otherwise SQLite is the obvious default.)


---

## 6. Sonnet's Task — `clude/rules.md`

Designed by Sonnet, written to `clude/rules.md` (created this session — go read it).

**Purpose:** make Claude Code behave as a **strict tutor and coaching coach** in this repo — explaining before doing, making you write the hard parts, and refusing to autopilot. It is the anti-vibe-coding contract for the project.

**Rule categories the file contains (9):**

1. **Role & Teaching Contract** — tutor first, generator second; you write the hard parts.
2. **How to Answer** — default response shape: Concept → Approach → (you) Implement → Review.
3. **Code-Writing Rules** — when Claude may write code vs. only guide; small diffs, never full-file dumps unprompted; learner-level comment density.
4. **Explanation Rules** — always explain WHY; define jargon on first use; connect to what you've already built.
5. **Do-Not-Do List** — no vibe coding, no silent rewrites, no skipped tests, no unexplained magic, no silent model swaps.
6. **Debugging Protocol** — Reproduce → Hypothesize → Check → Fix → Explain (coach, don't hand answers).
7. **Safety-Project-Specific Rules** — don't weaken filter/judges for convenience; **fail closed** on ambiguous verdicts; `banned.txt` is your domain.
8. **Git & Workflow Discipline** — one concept per commit/branch/PR; keep docs in sync.
9. **When to Escalate / Ask** — stop and ask one focused question rather than assume.

**Recommended file outline:** the nine numbered sections above, each a short heading followed by tight imperative bullets (one enforceable action per bullet).

**Writing-style choices (Sonnet's):** imperative second-person ("Explain before you edit", "Never dump") so rules read as enforceable commands, not aspirations; one action per bullet so a violation is unambiguous; project-specific jargon (`tokenization`, `banned.txt`, phase numbers) woven in so the file doubles as project context rather than a generic template. Keep it short (~120–180 lines) so it stays maintainable.


---

## 7. Build Order for the Whole Repo

1. **Refactor to a `guardrail/` package** (move logic out of the flat script). Small, boring, unlocks everything.
2. **Phase 2 hardening** — `call_model()` pure + error-handled.
3. **Phase 3a** input judge → wire pipeline.
4. **Phase 3b** output judge.
5. **Phase 4** CLI shell.
6. **Phase 5** SQLite logging + reports.
7. **Phase 4.5** Web API (only if you still want it).

Rule of thumb: **core logic first, transport last, storage around it.** Never build a shell before the thing it wraps works as a function.

Target repo shape by the end:

```
AI_Guardrail/
├── guardrail/            # the pure core (no I/O)
│   ├── __init__.py
│   ├── model.py          # call_model()
│   ├── judge.py          # judge_input(), judge_output()
│   ├── filter.py         # local banned-word check
│   ├── store.py          # SQLite logging (Phase 5)
│   └── prompts/          # judge system prompts as .txt
├── cli.py                # Phase 4 shell
├── api.py                # Phase 4.5 shell (optional)
├── reports.py            # Phase 5 reporting
├── tests/                # grows every phase
├── banned.txt
├── clude/rules.md        # Claude tutor rules
├── .env  .gitignore  README.md  ROADMAP.md
```

---

## 8. Suggested GitHub Milestone Structure

| Milestone | Closes when | Issues (examples) |
|-----------|-------------|-------------------|
| **M0: Refactor core** | logic lives in `guardrail/`, script still runs | "Create guardrail package", "Make call_model pure", "Remove global user_input" |
| **M1: Input Judge (3a)** | prompts classified by AI | "Write input judge system prompt", "Parse/normalize verdict", "Fail-closed on ambiguity", "Wire pipeline" |
| **M2: Output Judge (3b)** | AI answers are validated | "Write output judge", "Add output judge to pipeline", "Test unsafe-answer cases" |
| **M3: CLI** | tool runs from terminal | "argparse shell", "--explain/--no-model flags", "exit codes", "CLI tests" |
| **M4: Analytics** | decisions logged + queryable | "logs schema", "log_interaction()", "reports.py", "gitignore analytics.db" |
| **M5: Web API (optional)** | HTTP endpoint mirrors CLI | "FastAPI /check", "Pydantic models", "reuse core" |

Each milestone = one column on a GitHub Project board (Todo / In progress / Done).

---

## 9. Branch & PR Strategy (solo junior)

- **`main` is always runnable.** Never commit broken code to `main`.
- **One branch per issue/concept**, named `phase3a-input-judge`, `refactor-core`, etc. Small and short-lived.
- **Small PRs** — one concept each. If a PR touches the judge *and* the CLI *and* the DB, split it. A junior reviewing their own PR learns more from 5 small diffs than 1 giant one.
- **Self-review before merge:** open the PR, read your own diff top to bottom, write a one-line "what this does + how I tested it." Then merge.
- **Commit messages:** imperative, scoped — `feat(judge): add fail-closed input verdict parsing`.
- **Tag releases** at milestone boundaries (`v0.3`, `v0.4`) so you can see your own progress.
- Keep `.env` and `analytics.db` in `.gitignore` — verify before every push.

---

## 10. Next 3 Actions

1. **Create the `guardrail/` package and move existing logic into it** (M0) — no behavior change, just structure. This is the unlock for every later phase.
2. **Make `call_model()` a pure, error-handled function** (takes a prompt, returns text, no globals, no `print`).
3. **Write the Phase 3a input-judge system prompt** and `judge_input()` returning a normalized `SAFE`/`UNSAFE` verdict, failing closed on anything ambiguous.

---

## Bottom Line

- **Recommended default path:** Refactor into a pure `guardrail/` core → LLM-as-a-Judge (input then output) → **CLI** → SQLite analytics → *optional* Web API. Core logic first, transport last.
- **Biggest risk:** carrying the current script shape forward — the global `user_input`, `input()`/`print()` inside logic — into every later phase. Both Fable and the primary plan agree: if transport and logic stay tangled, the judge, the CLI, the API, and the tests all get harder, and "CLI first" quietly becomes "vibe coding with extra steps." Extracting a pure `process_prompt(prompt) -> Result` core is the single highest-leverage fix.
- **Single best next step:** Create the `guardrail/` package and move `call_model` / filter logic into it, unchanged, then confirm the script still runs. Everything else builds on that seam.
