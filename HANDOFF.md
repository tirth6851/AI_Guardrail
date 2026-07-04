# Session Handoff — AI Guardrail

**Date:** 2026-07-03 · **Phase:** 3 (redesigned) · **Status:** Mid-tutoring on the data-import stage for a NEW local safety classifier. Waiting on the developer to confirm 3 datasets (STEP 1 of 7).

---

## What changed this session

- **Major direction change (Phase 3):** dropped the external **Groq LLM-as-judge** as the Phase 3 input checker. Phase 3 is now a **local, self-owned binary text classifier** (SAFE / UNSAFE) acting as a gate before the main LLM. Not an LLM, not a chatbot — a *classifier wrapped in gate semantics*.
- **New public behavior (deliberate):** UNSAFE → print `"Prompt flagged"` and stop. No confidence scores, no reasons shown to the user (minimize information leakage).
- **Files created:**
  - `ROADMAP.md` — full 10-section roadmap (Phases 2→5). *Note: its Phase 3 section describes the older Groq-judge design and now needs a revision to reflect the local-classifier pivot.*
  - `clude/rules.md` — strict-tutor rules for Claude in this repo (designed by Sonnet). Path is literally `clude/` (not `.claude/`), as specified.
  - `.claude/commands/handoff.md` — the `/handoff` slash command (this procedure). `.claude/` is git-ignored, so it's local-only.
- **Datasets verified on Hugging Face Hub** for classifier training (see gotchas).

---

## Current architecture / direction

Pipeline as it stands now:

```
prompt → banned.txt filter (cheap) → LOCAL safety classifier (SAFE/UNSAFE)
       → if both pass → main LLM → (Phase 3b: output validator) → user
       → if flagged   → print "Prompt flagged", stop
```

- The classifier is the new work. The `banned.txt` filter stays as the cheap first pass.
- Phase 3b **output validator** still exists (folded in from the original two-layer "ultimate vision").
- **Docs-vs-reality flag:** `ROADMAP.md` Phase 3 still reads as "Groq judge." Update it when the classifier design is settled. Also: `promtVerification()` in `safety_guard.py` is **correct** — the old "returns on first word" note in CLAUDE.md/plan.md describes an already-fixed bug; do not chase it.

---

## Open decisions & deferred items

- **The 3 training datasets — NOT yet confirmed by developer.** Proposed:
  1. `SalKhan12/prompt-safety-dataset` — ungated, cleanest fit.
  2. `allenai/wildguardmix` — **gated** (decision needed: accept terms + HF token, or swap out).
  3. Third slot open: `lmsys/toxic-chat` **or** `PKU-Alignment/BeaverTails` **or** another verified one.
- **Model strategy (Phase 3, STEP 3) deferred:** rules baseline vs. classic ML (TF-IDF+LR) vs. small neural vs. small transformer. Guidance so far: start simplest, earn complexity via evaluation.
- **Phase 4 fork already resolved:** CLI first, Web API as optional Phase 4.5 (Fable-reviewed, in ROADMAP §5).

---

## Known gotchas (do not fall into these)

- **`allenai/wildguardmix` is GATED** 🔒 — the dataset viewer returns **404 without credentials**. That 404 means "accept terms + authenticate," NOT "doesn't exist." Needs an HF token.
- **SafetyPrompts is a listing/directory site, NOT a dataset.** It cannot be ingested. If used as "source 3," pick a concrete downloadable dataset it links to instead.
- **Licensing:** `toxic-chat` and `BeaverTails` are **CC-BY-NC** (non-commercial); `wildguardmix` is ODC-BY + gated. Fine for learning; constrains any future shipping.
- **`BeaverTails` labels QA pairs** (prompt+answer), not bare prompts — extra mapping work vs. `toxic-chat`.
- **Teaching mode is active:** Claude is a strict tutor here — explain first, minimal generic snippets only, make the developer write the real code, wait for understanding before advancing. See `clude/rules.md`.

---

## Next 3 actions

1. **Developer confirms the 3 datasets** (finishes STEP 1): accept/swap `wildguardmix`'s gate, and pick the third source by exact `author/name`.
2. **Proceed to STEP 2 — schema inspection:** inspect each dataset's fields and draft a unified minimum schema (`text`, `label`, `source`, optional `category`).
3. **Commit this session's docs** (see below) — currently all untracked/uncommitted.

---

## How to resume

```bash
cd AI_Guardrail
git status                      # ROADMAP.md, clude/, plan.md are untracked; .gitignore modified
# resume the tutoring thread: developer answers STEP 1 (confirm 3 datasets), then STEP 2

# when ready to commit the planning docs (ask developer first):
git add ROADMAP.md clude/ plan.md .gitignore HANDOFF.md
git commit -m "docs: add roadmap, tutor rules, Phase 3 local-classifier pivot handoff"
```

Uncommitted as of handoff: `ROADMAP.md`, `clude/rules.md`, `plan.md`, `HANDOFF.md`, `.gitignore` (modified). `.claude/commands/handoff.md` is local-only (git-ignored).
