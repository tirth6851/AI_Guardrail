"""
PII detection + redaction (regex baseline).

Scope note: this is a deliberately simple, dependency-free first pass — email,
phone, SSN, credit-card, IP. It is designed to be swapped for a heavier NER
engine (e.g. Presidio) later behind the SAME two functions, so the pipeline
never has to change. Regex catches the structured, high-value identifiers that
matter most for not logging/echoing secrets; it will miss free-form PII (names,
addresses), which is the documented limit of this layer.

Used in two places in the pipeline:
- redact the prompt BEFORE it is written to the audit log (store.py), so the
  log is not itself a PII database (trust boundary TB5).
- redact the model's OUTPUT before it reaches the user, so a model that echoes
  or fabricates an identifier doesn't leak it.
"""
import re

# (label, pattern) — order matters: match SSN before the looser phone pattern so
# "123-45-6789" is tagged SSN, not misread as a phone number.
_PATTERNS = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("PHONE", re.compile(r"\b(?:\+?\d{1,2}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}\b")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


def detect(text: str) -> list:
    """Return a list of (label, matched_text) for every PII span found."""
    found = []
    for label, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            found.append((label, match.group()))
    return found


def redact(text: str) -> tuple:
    """
    Replace every PII span with a [LABEL] placeholder.

    Returns (redacted_text, labels_found). Applies patterns in order and rewrites
    on the working string so an earlier, more specific pattern (SSN) wins over a
    later looser one (phone/credit-card) on overlapping digits.
    """
    labels = []
    for label, pattern in _PATTERNS:
        def _sub(m, _label=label):
            labels.append(_label)
            return f"[{_label}]"
        text = pattern.sub(_sub, text)
    return text, labels
