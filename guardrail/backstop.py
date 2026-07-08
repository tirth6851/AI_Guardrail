"""
Intent-gated weapons/CBRN backstop.

WHY NOT A FLAT WORD LIST: a bare "block if the text contains 'bomb'/'sarin'"
rule blocks "when was the atomic bomb dropped", "the sarin attack on Tokyo",
"handgun ownership laws" — history, news, and legal questions that are plainly
benign. Measured, that flat rule pushed the benign false-positive rate to 0.52.
The user chose Balanced-F1, so recall-at-any-FP-cost is the wrong trade.

WHAT THIS DOES INSTEAD: it flags only when a harmful term co-occurs with an
INSTRUCTIONAL / ACQUISITIONAL intent cue ("make", "build", "synthesize", "steps
to", "how to", ...). "how do I make a pipe bomb" -> blocked; "when was the atomic
bomb dropped" -> allowed. This targets exactly the failure the classifier has
(it under-scores instructional harmful prompts) without punishing benign mentions.

Terms come from harmful_terms.txt (same file, same format). The general ML
classifier still runs after this as the catch-all for harm this list doesn't name.
"""
import re
from pathlib import Path

from guardrail.judge import Verdict

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TERMS_FILE = _REPO_ROOT / "harmful_terms.txt"

# Instructional / acquisitional intent cues. A harmful term is only a backstop hit
# if one of these also appears — the signal that the user wants to DO the thing,
# not read about it. Word-boundaried so "get" doesn't match "target".
_INTENT = re.compile(
    r"\b(?:make|makes|making|made|build|builds|building|built|synthesi[sz]e|"
    r"construct|manufacture|produce|assemble|create|creating|brew|cook|cooking|"
    r"mix|prepare|detonate|deploy|weaponi[sz]e|obtain|acquire|buy|purchase|get|"
    r"craft|homemade|home-made|instructions?|steps?|guide|recipe|tutorial|"
    r"blueprint|how\s+to|how\s+do\s+i|how\s+can\s+i)\b",
    re.I,
)


def _load_terms() -> tuple:
    words, phrases = set(), []
    if not _TERMS_FILE.exists():
        return words, phrases
    for line in _TERMS_FILE.read_text(encoding="utf-8").splitlines():
        entry = line.strip().casefold()
        if not entry or entry.startswith("#"):
            continue
        (phrases.append(entry) if " " in entry else words.add(entry))
    return words, phrases


_TERM_WORDS, _TERM_PHRASES = _load_terms()


def backstop_check(text: str) -> Verdict:
    """UNSAFE only if a harmful term AND an instructional-intent cue both appear."""
    folded = text.casefold()
    tokens = set(re.findall(r"\w+", folded))
    term_hit = (
        not _TERM_WORDS.isdisjoint(tokens)
        or any(phrase in folded for phrase in _TERM_PHRASES)
    )
    if term_hit and _INTENT.search(folded):
        return Verdict("UNSAFE", "weapons/CBRN backstop: harmful term + instructional intent")
    return Verdict("SAFE", "no intent-gated harmful term")
