# AI Guardrail

A layered AI safety pipeline in pure Python. A user prompt passes through local,
offline-checkable defenses — normalization, a banned-word/backstop filter,
prompt-injection heuristics, and a trained ML classifier — before it's allowed
to reach the Groq API, and the model's answer is screened and PII-redacted
before it reaches the caller. The same core (`guardrail/`) is wrapped by two
interchangeable shells: a CLI (`cli.py`) and an HTTP API (`api.py`).

---

## Quickstart

```bash
pip install -r requirements.txt
# .env must contain GROQ_API_KEY=... (create it once; not part of this repo)

python cli.py "how do I write a resignation letter" --explain
python -m pytest
python eval/run.py
```

No `GROQ_API_KEY` yet? Add `--no-model` to `cli.py` to exercise the input-only
path (normalize → filter → backstop → injection → classifier) with no network
call — same thing `tests/` and `eval/run.py` do.

---

## Architecture

```
User Input
    ↓
normalize (unicode fold / leetspeak / zero-width strip / base64 decode)
    ↓
local_filter (banned.txt, phrase-aware)  +  backstop_check (harmful_terms.txt, intent-gated)
    ↓
injection_check (structural jailbreak heuristics)
    ↓
judge_input  ← TF-IDF + Logistic Regression classifier, threshold 0.30 (fail-closed)
    ↓ (if SAFE)
call_model  → Groq API (llama-3.3-70b-versatile)
    ↓
judge_output ← TF-IDF + Logistic Regression classifier, threshold 0.50
    ↓ (if SAFE)
pii.redact  → strip emails/SSNs/etc. from the answer
    ↓
Result(decision, answer, ...)  → returned to caller, logged to analytics.db
```

`guardrail/__init__.py` exposes two entry points:
- `screen_input(prompt) -> Result` — input-only path, no model call (used by `--no-model`, `eval/`, most of `tests/`).
- `process_prompt(prompt) -> Result` — the full pipeline above.

Both the CLI and the API call these same two functions — no safety logic is
duplicated or reimplemented in either shell.

### Classifier status — what's live vs. what was tried and rejected

- **Live path:** `guardrail/judge.py`'s TF-IDF + Logistic Regression classifiers
  (`guardrail/models/input_clf.joblib` / `output_clf.joblib`), trained on
  `wildguardmix` plus hand-written benign augmentation
  (`benign_augment.jsonl`). Current measured performance: macro-F1 **0.974**,
  severe (weapons/CBRN) recall **1.000**, benign false-positive rate **0.048**.
- **Evaluated, not integrated:** a DistilBERT transformer classifier
  (`train_transformer_classifier.py`, `guardrail/ml_input_classifier.py`,
  `eval/run_transformer_eval.py`, `eval/run_combined_eval.py`). It scored
  better in aggregate on `eval/corpus/` than the *pre-augmentation* TF-IDF
  baseline, but regressed a specific hardened regression-test anchor case
  (`tests/test_gate.py`'s "how do I kill a Linux process that is stuck") — a
  named, deliberately protected invariant. A better aggregate score did not
  justify integrating a model that broke it. Kept in the repo as reproducible
  research code; not called from `guardrail/__init__.py`. OR/AND-gating the
  two classifiers together was also measured and rejected — see
  `HANDOFF.md`/`CLAUDE.md` for the full numbers and reasoning.

### API / auth / policy / abuse-control status

All of the following are implemented and covered by tests — **not** a design
sketch:

- **HTTP API** (`api.py`) — `POST /check`, `GET /health`. Thin FastAPI shell;
  no safety logic lives here.
- **Tenant identity** (`guardrail/policy.py`) — a simple API-key → tenant
  mapping. **No OAuth, no multi-user login** — deliberately local-first and
  simple, per the project's scope.
- **Policy** (`TenantPolicy`) — every configured tenant currently gets the
  same default rate limit / offender-escalation thresholds; the config format
  doesn't yet support *different* limits per tenant (see Known Limitations).
- **Abuse controls** (`guardrail/abuse.py`) — an in-memory, single-process
  sliding-window rate limiter and a repeat-offender tracker, both keyed by
  `tenant_id`. Resets on process restart; not distributed (see Known
  Limitations).

---

## Running the CLI

```bash
python cli.py "your prompt"                 # full pipeline (calls Groq)
python cli.py "your prompt" --no-model       # input-only path, no Groq call
python cli.py "your prompt" --explain        # also print judge reasons/scores (local/dev only)
```

Exit code `0` if the prompt was answered safely, non-zero if it was flagged
(`UNSAFE`) or the model errored (`ERROR`). Every run is logged to
`analytics.db` via `guardrail/store.py`.

---

## Running the API

```bash
uvicorn api:app --reload
```

`GET /health` needs no auth (liveness probe). `POST /check` requires an
`X-API-Key` header — see **API-key usage** below.

### Example request

```bash
curl -X POST http://127.0.0.1:8000/check \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{"prompt": "how do I write a resignation letter", "no_model": true}'
```

Response:

```json
{
  "request_id": "b1e6...-...-...",
  "decision": "SAFE",
  "answer": "",
  "message": "OK"
}
```

Only the generic `message` and `answer` cross the HTTP boundary — the
detailed judge reason/score never does (same rule `cli.py --explain` follows
by keeping that detail local-only).

### API-key usage

Every `/check` call must send `X-API-Key: <your key>`.

- **No `GUARDRAIL_API_KEYS` configured?** The API falls back to one local-dev
  key so it's runnable out of the box: `X-API-Key: dev-local-key` (tenant
  `dev-local`). Don't rely on this outside local development.
- **To configure real keys**, set in `.env` or the environment:
  ```
  GUARDRAIL_API_KEYS=key1:tenant-a,key2:tenant-b
  ```
  Each key maps to one tenant; requests, rate limits, and offender tracking
  are all scoped to that tenant.
- Missing or unknown key → `401`. Tenant escalated (too many recent `UNSAFE`
  decisions) → `403`. Over the tenant's rate limit → `429`. Prompt over
  `MAX_PROMPT_BYTES` (8192) → `413`.

---

## Running tests

```bash
python -m pytest
```

Covers: the regression gate (`tests/test_gate.py` — severe recall, harmful
recall, macro-F1 floor, and named anchor cases that must never flip), pipeline
unit tests (`tests/test_pipeline.py`), the API layer including auth/rate
limiting/offender escalation (`tests/test_api.py`), tenant resolution
(`tests/test_policy.py`), and the rate limiter/offender tracker in isolation
(`tests/test_abuse.py`).

## Running evals

```bash
python eval/run.py
```

Scores `guardrail.screen_input()` against `eval/corpus/*.jsonl` (38 hand-built
cases across benign, benign-lookalike, injection, and weapons/CBRN
categories) — no Groq call, no cost. Reports harmful recall, severe-category
recall (the hard gate), benign false-positive rate, and macro-F1.

---

## Environment variables (documented only — `.env` already exists locally)

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | yes, for the full pipeline | Groq API auth (`guardrail/model.py`). Not needed for `--no-model`/`screen_input`-only use. |
| `GUARDRAIL_HASH_SALT` | no (has an obvious dev default) | Salts the SHA-256 hash of logged prompts (`guardrail/store.py`). Set a real value outside local dev. |
| `GUARDRAIL_API_KEYS` | no (has a dev fallback) | `key:tenant_id` pairs, comma-separated, for the API's tenant identity (`guardrail/policy.py`). |

---

## Known limitations / not yet built

- **No OAuth or multi-user login** — API-key tenant identity only, by design.
- **No per-tenant policy overrides** — all tenants share one default rate
  limit / offender-escalation threshold; the config format has no per-tenant
  override yet.
- **Abuse-control state is in-memory, single-process** — resets on restart;
  not safe to run with multiple uvicorn workers (`--workers > 1`) since each
  worker would keep independent, weaker-in-aggregate limits.
- **No dependency lockfile** — `requirements.txt` pins minimum versions, not
  exact ones; no `pyproject.toml`.
- **One documented, accepted false positive:** "the movie was a total bomb at
  the box office" (an idiom; different pattern class from the fixed
  "explain/write X" false-positive family — see `eval/corpus/benign_lookalike.jsonl`).
- **Transformer classifier is research-only** — trained, evaluated, and
  deliberately not wired into the live pipeline (see Architecture above).
- **Tool/RAG readiness** — not built; the pipeline currently trusts model
  output as the only untrusted-content boundary. If tool-call or
  retrieved-document content is added later, it should be treated as
  untrusted input requiring its own screening, not appended to a trusted
  prompt.
- **No requirements/dependency automation for the transformer research path**
  (`torch`/`transformers`) — intentionally not installed by default; see
  `requirements.txt`'s commented-out section.

Full session-by-session history and the numbers behind every decision above
are in `HANDOFF.md`; project-structure/contributor guidance is in `CLAUDE.md`;
the original phased plan (partly superseded, noted where it is) is in
`ROADMAP.md` and `plan.md`.
