"""
Deterministic word/phrase gate — the cheapest layer, runs first.

Two changes from the original single-token version, both fixing real bugs found
in review:

1. PHRASE MATCHING. The old code did one whole-file `.split()`, so a multi-word
   banned entry like "bullet vibe" silently became two single-word bans — making
   the ordinary word "bullet" flag "add a bullet point". Now each *line* is one
   entry: a single word matches a whole token; a multi-word line matches only as
   a contiguous phrase. "bullet vibe" no longer bans "bullet".

2. PACKAGE-RELATIVE PATHS. The old `open("banned.txt")` only worked when the
   process happened to be started from the repo root. Paths are now resolved
   relative to this file, so the core works when imported as a library too.

Two lists feed this gate:
- banned.txt         — the legacy profanity/obscenity list (unchanged content).
- harmful_terms.txt  — the safety backstop for weapons/CBRN terms the ML
  classifier misses (see its header + HANDOFF.md for how the terms were chosen).
Both are optional; a missing file just contributes no entries.
"""
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_LIST_FILES = [_REPO_ROOT / "banned.txt", _REPO_ROOT / "harmful_terms.txt"]


def _load_entries() -> tuple[set, list]:
    """Read the list files once; split into single-word tokens and multi-word phrases."""
    words, phrases = set(), []
    for path in _LIST_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = line.strip().casefold()
            if not entry or entry.startswith("#"):  # skip blanks and comments
                continue
            if " " in entry:
                phrases.append(entry)
            else:
                words.add(entry)
    return words, phrases


# Loaded at import time (read-only, safe to share). Retrained/edited lists need a
# fresh process — same lifecycle as the joblib models in judge.py.
_BANNED_WORDS, _BANNED_PHRASES = _load_entries()


def _tokenize(text: str) -> list:
    # split on non-word runs so "Hack!" and "hack" match the same entry.
    return [t for t in re.split(r"(\W+)", text.casefold()) if t.strip()]


def local_filter(prompt: str) -> bool:
    """Return True if prompt is safe (no banned word/phrase found), False if flagged."""
    folded = prompt.casefold()
    # phrase check: substring match on the raw (folded) text so word order matters.
    for phrase in _BANNED_PHRASES:
        if phrase in folded:
            return False
    # word check: exact token match, so "bass" never matches "ass".
    tokens = set(_tokenize(prompt))
    return _BANNED_WORDS.isdisjoint(tokens)
