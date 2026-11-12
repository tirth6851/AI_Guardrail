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
  "how to make a bomb" should not get a free pass. Payloads are decoded up to a few
  layers deep (base64 of base64, hex of base64, ...), with caps on depth and count.

A third helper, injection_forms(variants), adds a more aggressive leetspeak form
that is ONLY meant for the injection heuristics (see its docstring).
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

# Extra swaps used ONLY by injection_forms() (never by normalize()/expansions(),
# which also feed the word filter and weapons backstop): 1->i, 5->s, 7->t. They
# are what "1gnore prev1ous 1nstruct1ons" needs, but too lossy to apply globally.
_LEET_INJECTION = {**_LEET, ord("1"): "i", ord("5"): "s", ord("7"): "t"}

# How many layers of encoding to unwrap. This is the only cap: each layer's decoded
# text is shorter than the text it came from, so the total work stays bounded, and
# there is deliberately NO cap on the NUMBER of payloads (a count cap would silently
# stop screening whatever came after the first N blobs).
_MAX_DECODE_DEPTH = 3

# A run of base64-ish characters long enough to plausibly hide a short word
# (>= 12 chars = 9 decoded bytes). The strict validate=True + text guards in
# _decode_candidates reject the many benign runs that merely look base64-ish.
_B64_RUN = re.compile(r"[A-Za-z0-9+/]{12,}={0,2}")
# The URL-safe alphabet (-_ instead of +/). A SEPARATE pattern from _B64_RUN so that a
# standard blob with a "-" or "_" glued next to it ("id_<blob>") is still found by
# _B64_RUN exactly as before, rather than being swallowed into one longer run.
_B64URL_RUN = re.compile(r"[A-Za-z0-9_-]{12,}={0,2}")
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


def _looks_like_text(decoded: str) -> bool:
    """True if decoded bytes look like a human message rather than binary junk."""
    # str.isprintable() is False for "\n", "\t" and for Unicode space separators
    # (NBSP, EM SPACE, IDEOGRAPHIC SPACE), so a payload using any of them used to be
    # thrown away unscreened. Allow those; _fold() collapses them to a plain space.
    def _ok(c: str) -> bool:
        return c.isprintable() or c in "\n\r\t" or unicodedata.category(c) == "Zs"

    return any(c.isalpha() for c in decoded) and all(_ok(c) for c in decoded)


def _decode_candidates(blob: str) -> list[str]:
    """Every way blob decodes to text: base64 (standard or URL-safe, padded or not)
    and/or hex. A hex string is also valid base64 characters, so both are tried."""
    out = []
    try:
        s = blob.rstrip("=").replace("-", "+").replace("_", "/")
        if len(s) % 4 != 1:  # a length of 1 mod 4 can never be valid base64
            s += "=" * (-len(s) % 4)  # attackers can simply drop the "=" padding
            decoded = base64.b64decode(s, validate=True).decode("utf-8")
            if _looks_like_text(decoded):
                out.append(decoded)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        pass
    try:
        decoded = bytes.fromhex(re.sub(r"\s+", "", blob)).decode("utf-8")
        if _looks_like_text(decoded) and decoded not in out:
            out.append(decoded)
    except (ValueError, UnicodeDecodeError):
        pass
    return out


def _decode_payloads(text: str) -> list[str]:
    """Decoded base64/hex payloads found in text, unwrapping nested layers
    (base64 of base64, hex of base64, ...) up to _MAX_DECODE_DEPTH. Raw
    (case-preserved) text, as base64 is case-sensitive."""
    found: list[str] = []
    seen = {text}
    queue = [(text, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth >= _MAX_DECODE_DEPTH:
            continue
        for pattern in (_B64_RUN, _B64URL_RUN, _HEX_RUN):
            for match in pattern.findall(current):
                for decoded in _decode_candidates(match):
                    if decoded in seen:
                        continue
                    seen.add(decoded)
                    found.append(decoded)
                    queue.append((decoded, depth + 1))
    return found


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
    for decoded in _decode_payloads(text):
        out.extend([normalize(decoded), _fold(decoded)])
    # dedupe while preserving order (variants[0] must stay the canonical form).
    seen, unique = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def injection_forms(variants: list[str]) -> list[str]:
    """
    `variants` (from expansions()) plus a more aggressively de-leeted copy of each
    (1->i, 5->s, 7->t on top of normalize()'s swaps), deduped, order preserved.

    ONLY for the injection heuristics. normalize() deliberately does not map those
    digits globally because it corrupts ordinary text and expansions() also feeds
    the word filter and weapons backstop, where that would risk false positives.
    The injection regexes need specific multi-word phrases, so a lossy extra view
    costs little there and catches "1gnore prev1ous 1nstruct1ons".
    """
    seen, out = set(), []
    for v in variants:
        for form in (v, v.translate(_LEET_INJECTION)):
            if form not in seen:
                seen.add(form)
                out.append(form)
    return out
