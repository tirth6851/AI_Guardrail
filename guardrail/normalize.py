"""
Input canonicalization — runs BEFORE any matcher (filter, classifier) sees text.

Why this exists: every layer downstream is only as good as the canonical form it
is handed. "b0mb", "b​omb" (zero-width space), or a base64 blob all sail past a
word-list and a bag-of-words classifier if the text isn't normalized first. This
module turns those surface tricks back into their plain form so the real detectors
get a fair look.

Two public functions:
- normalize(text): one cleaned string (unicode-folded, de-leeted, whitespace-collapsed).
- expansions(text): normalize() PLUS any decoded payloads (base64/hex) found inside,
  so the caller can screen the decoded content too — an attacker who base64-encodes
  "how to make a bomb" should not get a free pass.
"""
import base64
import binascii
import re
import unicodedata

# Characters that carry no visible meaning but break up tokens so a word-list
# misses them (zero-width space/joiner, BOM, soft hyphen). Strip them entirely.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)

# Common "leetspeak" digit/symbol substitutions. Deliberately conservative: only
# the swaps that are almost always evasion, not ones that wreck ordinary text.
# (We do NOT map 1->l or 5->s globally — too many false rewrites in real prompts.)
_LEET = str.maketrans({"0": "o", "3": "e", "4": "a", "@": "a", "$": "s", "!": "i"})

# A run of base64-ish characters long enough to plausibly hide a short word
# (>= 12 chars = 9 decoded bytes). The strict validate=True + printable guards in
# _try_decode reject the many benign runs that merely look base64-ish.
_B64_RUN = re.compile(r"[A-Za-z0-9+/]{12,}={0,2}")
# A run of hex long enough to hide a word (>= 12 hex digits = 6 bytes).
_HEX_RUN = re.compile(r"\b(?:[0-9a-fA-F]{2}\s*){6,}\b")


def _fold(text: str) -> str:
    """Unicode fold + strip zero-width + casefold + collapse whitespace. NO leet."""
    # NFKC folds compatibility variants (e.g. fullwidth "ｂｏｍｂ" -> "bomb").
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ZERO_WIDTH)  # drop invisible token-splitters
    text = text.casefold()  # lowercase, unicode-aware
    return re.sub(r"\s+", " ", text).strip()  # collapse runs of whitespace


def normalize(text: str) -> str:
    """The aggressive canonical form: _fold PLUS leetspeak undone (b0mb -> bomb)."""
    # kept separate from _fold because the leet swap (e.g. 4->a) corrupts
    # legitimate alphanumeric tokens like "c4"/"ak47" — the word filter needs the
    # un-leeted _fold form to match those, and the leet form to match "b0mb".
    return _fold(text).translate(_LEET)


def _try_decode(blob: str) -> str | None:
    """Return decoded text if blob is valid base64/hex printable ASCII, else None."""
    # base64 first (most common encoding attackers reach for).
    try:
        raw = base64.b64decode(blob, validate=True)
        decoded = raw.decode("utf-8")
        # only treat it as a hidden message if it's mostly printable text
        if decoded.isprintable() and any(c.isalpha() for c in decoded):
            return decoded
    except (binascii.Error, UnicodeDecodeError, ValueError):
        pass
    # then hex.
    try:
        raw = bytes.fromhex(re.sub(r"\s+", "", blob))
        decoded = raw.decode("utf-8")
        if decoded.isprintable() and any(c.isalpha() for c in decoded):
            return decoded
    except (ValueError, UnicodeDecodeError):
        pass
    return None


def expansions(text: str) -> list[str]:
    """
    Every canonical form the downstream matchers should screen, deduped.

    Includes BOTH the leet-normalized form (catches "b0mb") and the light _fold
    form (preserves "c4"/"ak47" for the word backstop), plus any base64/hex
    payload decoded from inside the text (each in both forms). The FIRST element
    is always normalize(text) — the classifier/injection layers use variants[0]
    as the single canonical string.
    """
    out = [normalize(text), _fold(text)]
    for pattern in (_B64_RUN, _HEX_RUN):
        for match in pattern.findall(text):
            decoded = _try_decode(match)
            if decoded:
                out.extend([normalize(decoded), _fold(decoded)])
    # dedupe while preserving order (variants[0] must stay the canonical form).
    seen, unique = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique
