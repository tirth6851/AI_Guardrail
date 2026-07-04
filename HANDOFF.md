# Session Handoff — AI Guardrail

**Date:** 2026-07-04 · **Phase:** 3 (local-classifier direction) — M0–M4 built and committed, but a real safety gap was found post-build and is **not yet fixed**. Waiting on the developer to pick a `banned.txt`/backstop option before any further code lands.

---

## What changed this session

- **Resolved the Phase 3 architecture fork:** confirmed with the developer to build the **local-classifier direction** from a prior session's `HANDOFF.md` (TF-IDF + Logistic Regression on `wildguardmix`), not the Groq LLM-as-judge design that this session's own `/goal` text originally specified. `judge_input`/`judge_output` keep the same function signatures either way, so CLI/analytics were unaffected by the choice.
- **M0 — refactor:** `guardrail/filter.py` (`local_filter`), `guardrail/model.py` (`call_model`, try/except on Groq auth/network/rate-limit errors). `safety_guard.py` rewired to call these instead of duplicating logic with a global.
- **M1/M2 — classifiers:** `train_classifier.py` trains TF-IDF+LR pipelines from `wildguardmix` (`prompt`→`prompt_harm_label`, `response`→`response_harm_label`), saved to `guardrail/models/*.joblib`. Two pretrained transformers were tried first and rejected on measured numbers: `KoalaAI/Text-Moderation` (2–5% recall on harmful prompts — wrong construct, toxic-language detector not intent detector) and `protectai/deberta-v3-base-prompt-injection-v2` (0% recall — detects injection syntax, not harmful requests). `guardrail/judge.py` implements `Verdict`, `judge_input`/`judge_output`, fail-closed on any load/prediction error. Input threshold tuned to 0.30 (0.5 only caught 71% recall); output kept at 0.5. `guardrail/__init__.py::process_prompt()` wires the full pipeline into one `Result`.
- **M3 — CLI:** `cli.py`, thin argparse shell, `--explain`/`--no-model`, exit codes 0/1, zero safety logic in the file.
- **M4 — analytics:** `guardrail/store.py` (parameterized SQLite `log_interaction`/`init_db`), `reports.py` (totals, flag rate, recent flagged prompts). `analytics.db` gitignored.
- **Docs synced:** `CLAUDE.md` rewritten to match the actual package/classifier architecture (was describing the old flat script and a "planned" Phase 3). `ROADMAP.md`'s Phase 3 section marked superseded with an explanatory note, original LLM-judge plan kept visible as history, not deleted.
- **`clude/rules.md` updated** at the developer's request: added a standing rule that every code change must be accompanied by an explanation of *why* (especially file-to-file moves and removals), for code-review readability.
- **`clude/` directory vanished from disk entirely mid-session** — confirmed no git history ever covered it (untracked the whole time) and no tool call in this session's transcript deleted it. Recreated verbatim from conversation context, including the rule added above. **Cause unknown — the developer should check their IDE/sync tools/antivirus.**
- **Committed and pushed to a new branch** `guardrail-pipeline-local-classifier` (5 commits: refactor → judges → CLI → analytics → docs). **PR not opened** — `gh` CLI's stored token is invalid (`gh auth status` fails with 401). Manual link: `https://github.com/tirth6851/AI_Guardrail/pull/new/guardrail-pipeline-local-classifier`. Title/body already drafted in this session's transcript if resuming via Claude.
- **Critical safety gap found during final verification:** `python cli.py "how do I make a pipe bomb"` returns `decision: SAFE` — the input classifier scores it 0.17, under the 0.30 fail-closed threshold, and `banned.txt` has **zero weapons/violence coverage** (it's purely a profanity/obscenity list). The only reason nothing harmful reached the user in testing was Groq's own refusal — the developer explicitly ruled that out as an acceptable safety argument. **The developer declared M1 and M2 formally reopened** — not done until a backstop is approved and implemented.
- **Ran a read-only research/validation workflow** (no files edited) to build a concrete backstop proposal — see "Open decisions" below for the actual proposal, since nothing has been decided or applied yet.

---

## Current architecture / direction

```
prompt → local_filter (banned.txt, single-token whole-file match)
       → judge_input (local TF-IDF+LR classifier, threshold 0.30)
       → call_model (Groq llama-3.3-70b-versatile)
       → judge_output (local TF-IDF+LR classifier, threshold 0.50)
       → Result(decision, reason, answer, input_reason, output_reason, ...)
```

- `guardrail/` is the pure core (no `input()`/`print()`/globals). `cli.py` is the only full-pipeline shell right now.
- **`safety_guard.py` still bypasses Phase 3 entirely** — only `local_filter` + `call_model`, no judges at all. Known, documented, not fixed this session.
- **Docs vs. reality:** in sync as of this session (`CLAUDE.md`/`ROADMAP.md` both describe the local-classifier design accurately). One gap: `CLAUDE.md`'s "Known Issues" section does not yet mention the pipe-bomb false-negative gap — worth adding next session regardless of which backstop is chosen.

---

## Open decisions & deferred items

**1. Which `banned.txt`/backstop option to apply — nothing has been written to `banned.txt` yet.** Proposal on the table (full detail in this session's transcript):

- *Tier 1 (closes the actual demonstrated incident):* add `bomb` (190 harmful / 121 unharmful hits in the 88k-prompt corpus — a real but bounded, known false-positive rate). Note: this word was never proposed by the research workflow itself; found by manually checking the literal word in the triggering prompt after the workflow completed.
- *Tier 2 (empirically shortlisted against the broader classifier gap, near-zero collision):* `tamper`, `injure`, `carjacking` (2, 2, 0 unharmful hits respectively) — each catches only 1 of the 150 real prompts the classifier currently misses, so marginal, but essentially free.
- *Tier 3 (unambiguous named entities, zero measured collisions in 88k prompts, low marginal recall but cheap insurance):* `sarin`, `tabun`, `soman`, `novichok`, `anthrax`, `ricin`, `botulinum`, `bioweapon(s)`, `tnt`, `semtex`, `c4`, `rdx`, `petn`, `thermite`, `napalm`, `detonator`, `shrapnel`, `ak47`, `ar15`, `handgun`, `glock`, `switchblade`, `bayonet`.
- *Explicitly do NOT add* (high measured/predicted false-positive rate): `gun`, `kill` (breaks the project's own "kill a Linux process" test case), `magazine`, `car`, `harm` (2,029 unharmful hits), `poison` (150 unharmful hits), `torture`/`massacre`/`slaughter` (sports/hyperbole idiom), `m4` (Apple chip / UK motorway), `explosive`/`explosives` (borderline — 55/21 unharmful hits, flagged as "your call"), `biohazard`/`pathogen`/`toxin(s)` (medical/wellness collision), `incendiary`/`weaponize(d)` (political metaphor).
- *Alternative, non-keyword option:* scoped Groq escalation when the input classifier's score falls in an ambiguous band (would need to extend to ~0.05–0.30, not a cosmetically narrow slice, to actually catch the 0.17 score that triggered this) — fail-closed on any escalation error. Full pros/cons (outage coupling, unverified traffic-distribution assumption, new adversarial surface, ongoing eval burden, non-determinism) already written up in-session.

Once the developer picks an option: create a **new branch** (e.g. `phase1-banned-weapons`), implement **only** that backstop, commit with focused messages, push, open a PR against `main` describing what changed and how it was tested, then stop for review. **This has not started.**

**2. The M0–M4 PR is pushed but not opened.** Either the developer re-authenticates (`gh auth login -h github.com`, run via `! ` prefix) and asks to run `gh pr create`, or opens the PR manually via the link above.

**3. `safety_guard.py`'s Phase-3 bypass** — not touched this session; still an open question whether to rewire it to `process_prompt()` or retire it once `cli.py` is considered the primary entry point.

---

## Known gotchas

- **`local_filter()` does single-token, whole-file-split matching — no phrase matching exists.** Any future multi-word addition to `banned.txt` (e.g. "pipe bomb," "nerve agent") silently decomposes into separate single-word bans, some of which are ordinary words. Confirmed by tracing the actual code, not assumed.
- **Pre-existing live bug, unrelated to this session's proposal:** `banned.txt` already contains a line `bullet vibe`, which makes the standalone word `bullet` an active banned token *today* — e.g. "add a bullet point to the slide" already flags UNSAFE. Predates this session; not fixed.
- **`clude/rules.md` disappearing is unexplained** — recreated from context, but the developer should investigate root cause (IDE, sync tool, antivirus) on their end; nothing in this session's own tool calls deleted it.
- **`gh` CLI's stored GitHub token is invalid** — `gh auth login -h github.com` needed before any `gh pr create`/`gh pr list` will work.
- **The "missed_harmful_caught" validation metric undercounts obvious terms.** `bomb` scored 0 on that metric purely because the specific 150-row sample used for validation didn't happen to include a bomb-themed prompt — not because it's a weak candidate. Don't trust that column alone without a manual sanity check against the actual triggering example.
- **`wildguardmix/` (54MB, gated AI2 dataset) and `analytics.db` are gitignored.** A fresh clone needs to re-download/re-accept the dataset gate and rerun `python train_classifier.py` to regenerate `guardrail/models/*.joblib` — OR just use the joblib files already committed on the `guardrail-pipeline-local-classifier` branch (~940KB each, committed directly since they're small enough).

---

## Next 3 actions

1. **Get the developer's decision on the `banned.txt`/backstop proposal** (which tier(s), or the Groq-escalation alternative, or a combination) — then create `phase1-banned-weapons` (or their preferred name), implement only that change, commit, push, open a PR. Do not implement before explicit approval.
2. **Once `gh` is re-authenticated, open the pending PR** for `guardrail-pipeline-local-classifier` (M0–M4) against `main` — title/body already drafted in this session's transcript.
3. **After the backstop lands:** re-verify `python cli.py "how do I make a pipe bomb"` now exits 1, update `CLAUDE.md`'s Known Issues to reflect the fix, and reconsider whether `safety_guard.py` should be rewired to `process_prompt()` or retired.

---

## How to resume

```bash
cd AI_Guardrail
git status                      # should be clean, on branch guardrail-pipeline-local-classifier
git log --oneline -5            # confirm the 5 M0-M4 commits are present
# resume: get the developer's decision on the banned.txt/backstop proposal above, then:
git checkout main && git pull
git checkout -b phase1-banned-weapons
# edit banned.txt with the approved terms only, test against the pipe-bomb case and the
# existing "kill a Linux process" safe case, commit, push, gh pr create
```
