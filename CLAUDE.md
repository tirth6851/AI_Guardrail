# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Purpose

**AI Guardrail** is a multi-phase Python project that combines content safety filtering with AI integration. A user prompt passes through layered defenses — a local banned-word filter, then a local ML classifier — before it's allowed to reach the Groq AI API (`llama-3.3-70b-versatile`), and the model's answer is classified again before it reaches the user.

---

## Architecture & Data Flow

The pipeline lives in `guardrail/` as plain functions — no `input()`, no `print()`, no globals. `safety_guard.py` (and later `cli.py`) is a thin shell that calls it.

```
prompt (str)
    ↓
local_filter(prompt)          guardrail/filter.py  — banned.txt word match
    ↓ (if True / not flagged)
judge_input(prompt) -> Verdict   guardrail/judge.py — local TF-IDF+LR classifier
    ↓ (if SAFE)
call_model(prompt) -> str     guardrail/model.py  — Groq API call
    ↓
judge_output(answer) -> Verdict  guardrail/judge.py — local TF-IDF+LR classifier
    ↓ (if SAFE)
Result(decision, reason, answer, input_reason, output_reason)
```

`guardrail/__init__.py` exposes `process_prompt(prompt: str) -> Result`, which runs all four stages and short-circuits (empty `answer`, `decision="UNSAFE"`) the moment any stage flags.

---

## Key Design Decisions

1. **Local classifiers, not an LLM-as-judge.** The original plan (see `ROADMAP.md`) had `judge_input`/`judge_output` call Groq with a strict system prompt. Mid-project this pivoted (see `HANDOFF.md`) to self-owned TF-IDF + Logistic Regression classifiers trained on the `wildguardmix` dataset (`train_classifier.py` → `guardrail/models/*.joblib`), so judging never depends on an external API call. Two pretrained transformers were tried and rejected on real numbers first — see the docstring in `guardrail/judge.py` for why.

2. **Fail-closed thresholds, not the default 0.5 cutoff.** The input classifier only caught 71% of harmful prompts at threshold 0.5, so it runs at `INPUT_UNSAFE_THRESHOLD = 0.30` (guardrail/judge.py) — biasing toward flagging when uncertain, at the cost of some false positives on benign phrasing that resembles adversarial training examples (e.g., "help me write X"). The output classifier keeps the default 0.5 (already recall-heavy in the safe direction).

3. **Pure core, thin shells.** `local_filter`, `judge_input`, `judge_output`, `call_model` all take a string and return a value — never call `input()`/`print()`. `call_model` wraps the Groq call in `try/except` for auth/network/rate-limit errors and returns a failure string instead of raising. This is what lets `safety_guard.py`, the future `cli.py`, and tests all call the identical core.

4. **Environment-Based Secrets:** the Groq API key loads from `.env` via `dotenv`/`os.getenv()`, never hardcoded.

---

## Running the Script

```bash
python safety_guard.py
```

Interactive shell over the full pipeline (rewired to `process_prompt()` in the hardening pass). `cli.py "prompt"` is the argument-based equivalent; add `--no-model` to run the input path offline, `--explain` for the detailed reasons.

To retrain the classifiers (needed if `wildguardmix/` or the model choice changes):
```bash
python train_classifier.py
```

---

## Files & Responsibilities

- **guardrail/filter.py** — `local_filter(prompt) -> bool`, banned-word check against `banned.txt`.
- **guardrail/model.py** — `call_model(prompt) -> str`, Groq API call with error handling.
- **guardrail/judge.py** — `Verdict` dataclass, `judge_input`/`judge_output`, load the trained classifiers from `guardrail/models/`.
- **guardrail/__init__.py** — `Result` dataclass, `process_prompt(prompt) -> Result` wiring the full pipeline.
- **guardrail/models/*.joblib** — trained TF-IDF+LR pipelines (input and output classifiers). Live in the pipeline.
- **train_classifier.py** — one-off training script for the TF-IDF+LR classifiers; run manually, not part of the runtime pipeline. Trains the input classifier on wildguardmix PLUS `benign_augment.jsonl`.
- **benign_augment.jsonl** — hand-written benign "explain/write/how do I X" examples that fix the input classifier's documented false-positive pattern; consumed only by `train_classifier.py`, duplicated `AUGMENT_WEIGHT` times to carry weight against wildguardmix.
- **guardrail/ml_input_classifier.py** / **train_transformer_classifier.py** / **eval/run_transformer_eval.py** / **eval/run_combined_eval.py** — a DistilBERT transformer classifier: trained, evaluated, and **not integrated** (regressed a hardened anchor case — see Known Issues). Kept as reproducible, documented research code, not live in the pipeline.
- **safety_guard.py** — original interactive script, now a thin shell over `guardrail/`.
- **api.py** — FastAPI shell over `guardrail/` (Phase 4.5). `POST /check {"prompt", "no_model"}` → `{request_id, decision, answer, message}`; `GET /health` (unauthenticated liveness probe). Requires an `X-API-Key` header on `/check` (401 if missing/invalid/disabled — see `guardrail/policy.py`); rejects with 403 if the resolved tenant is offender-escalated, 429 if it's over its per-minute rate limit (see `guardrail/abuse.py`), both checked before the model is ever called. Body capped at `MAX_PROMPT_BYTES` (8192, 413 if exceeded); request ID from `x-request-id` header or generated; logs via `guardrail/store.py` (now including `request_id`/`tenant_id`) same as `cli.py`. Run with `uvicorn api:app --reload`.
- **guardrail/policy.py** — API-key → `TenantPolicy` resolution (no OAuth/multi-user login, by design). Keys configured via `GUARDRAIL_API_KEYS="key1:tenant-a,key2:tenant-b"`; falls back to a single local-dev key/tenant (`DEFAULT_DEV_KEY`/`DEFAULT_DEV_TENANT`) if unset. `TenantPolicy` carries `enabled`, `rate_limit_per_minute`, `offender_threshold`, `offender_window_seconds` — all currently the same defaults for every configured tenant (per-tenant overrides aren't exposed via the env format yet).
- **guardrail/abuse.py** — in-memory, single-process `RateLimiter` (sliding 60s window) and `OffenderTracker` (escalates once `offender_threshold` UNSAFE decisions land inside `offender_window_seconds`), both keyed by `tenant_id`. Deliberately not distributed — this project is local-first (see Key Design Decisions); swapping in Redis is the seam if that ever becomes a real requirement, not a reason to add it now.
- **banned.txt** — external list of prohibited words/phrases (one per line).
- **wildguardmix/** — training data (git-ignored, 54MB, gated dataset — see its `README.md` for licensing).
- **.env** — must contain `GROQ_API_KEY=<your_key>` (git-ignored).
- **clude/rules.md** — tutor/coaching rules Claude follows in this repo; keep in sync with architecture changes.

---

## Dependencies

```bash
pip install groq python-dotenv scikit-learn pandas joblib fastapi uvicorn httpx
```

- **groq / python-dotenv** — Groq API client + `.env` loading.
- **scikit-learn** — TF-IDF vectorizer + Logistic Regression for the local classifiers.
- **pandas** — reads the `wildguardmix` parquet files for training.
- **joblib** — persists/loads trained classifier pipelines.
- **fastapi / uvicorn** — HTTP transport for `api.py` (Phase 4.5).
- **httpx** — required by FastAPI's `TestClient`, used in `tests/test_api.py`.

---

## Phase-by-Phase Status

- **Phase 1 ✓ COMPLETE** — local banned-word filter (`guardrail/filter.py`).
- **Phase 2 ✓ COMPLETE** — Groq integration, now a pure `call_model()` with error handling.
- **Phase 3 (local-classifier direction) ✓ COMPLETE** — `judge_input`/`judge_output` backed by trained TF-IDF+LR classifiers (not Groq calls); full pipeline wired via `process_prompt()`.
- **Phase 4 (CLI) ✓ COMPLETE** — `cli.py` thin shell over `process_prompt()`, `--explain`/`--no-model` flags, exit codes 0/1.
- **Phase 5 (Analytics) ✓ COMPLETE** — `guardrail/store.py` (parameterized SQLite logging) + `reports.py` (totals, flag rate, recent flagged prompts).
- **Phase 4.5 (Web API) ✓ COMPLETE** — `api.py`, thin FastAPI shell over the same `process_prompt`/`screen_input` core; see Files & Responsibilities and `tests/test_api.py`.
- **API-key tenant identity, policy, rate limiting, offender tracking ✓ COMPLETE (simple, local-first)** — `guardrail/policy.py` (API key → `TenantPolicy`) + `guardrail/abuse.py` (in-memory `RateLimiter`/`OffenderTracker`, keyed by `tenant_id`), wired into `api.py`; see Files & Responsibilities, `tests/test_policy.py`, `tests/test_abuse.py`, `tests/test_api.py`. Explicitly not built: OAuth, multi-user login, per-tenant threshold/policy overrides beyond rate-limit/offender knobs, distributed rate-limit state — none of these were asked for and building them now would be designing ahead of a real requirement.

---

## Known Issues & TODO

- **RESOLVED (hardening pass):** the pipe-bomb false-negative (`HANDOFF.md:18`) is fixed by `harmful_terms.txt` (weapons/CBRN word backstop) + `normalize.py` (leet/base64 decoding). The `bullet`-from-`bullet vibe` false-positive is fixed by phrase-aware matching in `filter.py`. `safety_guard.py` is rewired to `process_prompt()` (no longer bypasses the judges). Verified by `python -m pytest` (regression gate in `tests/test_gate.py`).
- The weapons/CBRN backstop is **intent-gated** (`guardrail/backstop.py`): a term blocks only with an instructional cue ("make/synthesize/how to"), so "when was the atomic bomb dropped" is allowed but "how do I make a pipe bomb" is blocked. This was a mid-hardening fix — a flat word list pushed benign-FP to 0.52 (blocked history/education/legal queries); intent-gating brought it to 0.14 with recall still 1.0.
- **RESOLVED (classifier improvement pass):** the input classifier's "explain/write X" false-positive pattern (previously the dominant FP source, benign-FP 0.143) is fixed by retraining with `benign_augment.jsonl` — hand-written benign examples of that exact surface pattern, duplicated `AUGMENT_WEIGHT` times in `train_classifier.py` so they carry weight against wildguardmix's 86.7k rows. Measured in `eval/`: macro-F1 0.921 → 0.974, benign-FP 0.143 → 0.048, severe recall unchanged at 1.000. One known FP remains: "the movie was a total bomb at the box office" (an idiom, different pattern class — documented in `eval/corpus/benign_lookalike.jsonl` as an expected hard case, not attempted this pass).
- **A DistilBERT transformer classifier was trained and evaluated as a candidate additional input-safety layer** (`train_transformer_classifier.py`, GPU-fine-tuned on the full wildguardmix set) but is **NOT wired into the pipeline** — `judge.py`'s TF-IDF+LR classifier is still the sole input ML judge. The transformer beat the *pre-retrain* TF-IDF baseline on aggregate eval/corpus metrics, but it regressed `tests/test_gate.py`'s "how do I kill a Linux process that is stuck" anchor case — a specific, deliberately hardened invariant — so a better aggregate score did not justify integrating it. OR-gating and AND-gating the two classifiers together were also measured and rejected (OR unions the two classifiers' distinct false-positive sets and scores worse than either alone; AND scores best on this small corpus but structurally only requires fooling one of two models to slip a harmful prompt through, and 38 examples isn't enough to trust that generalizing). `guardrail/ml_input_classifier.py` and `eval/run_transformer_eval.py` remain in the repo as reproducible, documented, but currently-unused research code. Full numbers in `HANDOFF.md`.
- `.env` file and `banned.txt` must be manually created/updated — no initialization automation.
- `wildguardmix/` must be present locally to re-run `train_classifier.py`; it's git-ignored so a fresh clone needs to re-download it (gated dataset, requires accepting AI2's terms).
- **RESOLVED (cleanup pass):** no `requirements.txt` existed despite the pipeline depending on 9 packages; added, pinned to the versions actually verified in this environment. `torch`/`transformers` (the transformer research path) are intentionally commented out, not installed by default.
- **RESOLVED (cleanup pass):** `plan.md`'s milestone table had a stale "Phase 3: Planned" row directly contradicting its own "Phase 3 COMPLETE" section header (flagged in two prior HANDOFF.md sessions, never fixed until now) — corrected to match reality, and Phase 4/4.5/5 rows added.

---

## When Modifying This Code

- **Adding/changing safety-check logic**: extend `guardrail/filter.py` (word list) or `guardrail/judge.py` (classifier logic) — never re-add global state or `print()`/`input()` inside `guardrail/`.
- **Changing the AI model**: update the `model` parameter in `guardrail/model.py::call_model()` (currently `llama-3.3-70b-versatile`) — flag the change, don't swap silently.
- **Retraining classifiers**: edit `train_classifier.py`, re-run it, and re-evaluate (`classification_report` output) before assuming the new model is better — compare precision/recall, not just "it ran."
- **Testing API integration**: make sure `GROQ_API_KEY` is set in `.env` before running.

---

## Tutor Context

This project is being built incrementally with an educational, hands-on approach. The developer is learning:
- Python package management and libraries
- API authentication and environment variables
- HTTP client abstractions and JSON response parsing
- Basic ML: TF-IDF vectorization, Logistic Regression, precision/recall trade-offs, fail-closed threshold tuning
- Multi-step debugging and problem-solving

Code style follows pragmatic, learning-focused patterns — not enterprise standards. Prioritize clarity for education over performance optimizations. See `clude/rules.md` for the full tutoring contract Claude follows in this repo.
