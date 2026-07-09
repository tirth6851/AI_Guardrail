"""
Cheap, deterministic prompt-injection / jailbreak heuristics.

This is NOT a replacement for the classifier — it's a fast pre-filter for the
lazy, high-signal attacks a bag-of-words model misses because they're about
*structure* ("ignore previous instructions", "you are now DAN") rather than
harmful *topic*. Regexes here are intentionally high-precision: a hit is a strong
signal, so we fail closed on it, but we keep the set small to avoid flagging
ordinary prompts that happen to say "ignore".

Returns a Verdict (same type judge.py uses) so the pipeline treats it uniformly.
"""
import re

from guardrail.judge import Verdict

# Each pattern targets a well-known jailbreak framing. Kept as (regex, label) so a
# flag can say *which* pattern matched — useful in logs and eval triage.
_PATTERNS = [
    (re.compile(r"ignore (?:all |any |your )?(?:previous|prior|above|earlier)\s+(?:instruction|prompt|rule|direction)", re.I), "ignore-previous-instructions"),
    (re.compile(r"disregard (?:all |the |your )?(?:previous|prior|above|system)", re.I), "disregard-prior"),
    (re.compile(r"\byou are (?:now )?(?:DAN|STAN|DUDE|an? unrestricted|an? unfiltered)\b", re.I), "roleplay-jailbreak-persona"),
    (re.compile(r"\b(?:do anything now|jailbreak mode)\b", re.I), "named-jailbreak-mode"),
    # "developer mode" alone is a legit Android/Chrome feature — only flag it when
    # paired with a bypass cue, so "enable developer mode on my phone" is allowed.
    (re.compile(r"developer mode\b.*\b(?:bypass|ignore|no (?:restriction|rule|filter|guideline)|unrestricted|jailbreak)", re.I), "developer-mode-jailbreak"),
    (re.compile(r"pretend (?:you are|to be|that you)\b.*\b(?:no (?:restriction|rule|filter|guideline)|can do anything)", re.I), "pretend-no-restrictions"),
    (re.compile(r"\b(?:reveal|print|show|repeat|output)\b.*\b(?:system prompt|your (?:instruction|prompt|rule)s?|initial prompt)\b", re.I), "system-prompt-exfiltration"),
    (re.compile(r"\bact as\b.*\b(?:no (?:restriction|filter|limit)|without (?:restriction|filter|ethic))", re.I), "act-as-unrestricted"),
]


def injection_check(text: str) -> Verdict:
    """Return UNSAFE with the matched pattern label if a jailbreak framing is found."""
    for pattern, label in _PATTERNS:
        if pattern.search(text):
            return Verdict("UNSAFE", f"injection heuristic matched: {label}")
    return Verdict("SAFE", "no injection pattern matched")
