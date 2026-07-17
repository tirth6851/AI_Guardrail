"""
Emotional-manipulation / social-engineering heuristics for multi-turn chat.

WHY THIS EXISTS, SEPARATE FROM injection.py: injection.py catches structural
jailbreak framing ("ignore previous instructions", "you are now DAN") in a
single message. This module catches a different attack shape that only shows
up — or gets more effective — across a SESSION: guilt-tripping, false claims
of prior consent ("you already agreed to this"), manufactured urgency/distress
("if you don't help me something bad will happen"), and fictional reframing
used specifically to launder a request past the model's judgment ("it's just
a story so the rules don't apply"). None of these are about topic (the
classifier's job) or single-message structure (injection.py's job) — they're
about wearing down judgment over turns, which is exactly the failure mode
long chat sessions are documented to have.

Same shape as injection.py: high-precision regexes, fail closed on a hit,
returns a Verdict so the pipeline treats it uniformly. guardrail/session.py
runs this per-turn AND over recent session history, since an escalation
pattern ("you said yes last time", "we already agreed") only exists across
turns, not within one message alone.
"""
import re

from guardrail.judge import Verdict

_PATTERNS = [
    (re.compile(r"\byou (?:already |previously )?(?:agreed|said yes|gave (?:me )?permission|consented)\b", re.I), "false-prior-consent"),
    (re.compile(r"\bwe(?:'ve| have)? already (?:established|agreed|been through this)\b", re.I), "false-established-precedent"),
    (re.compile(r"\bif you don'?t (?:help|answer|tell) me,?\s+(?:something (?:bad|terrible)|i)\b", re.I), "manufactured-urgency-threat"),
    (re.compile(r"\byou'?re the only one who can help me\b", re.I), "manufactured-sole-dependence"),
    (re.compile(r"\byou (?:don'?t|do not) (?:really )?care about me\b", re.I), "guilt-appeal"),
    (re.compile(r"\bi (?:will|'ll) (?:be (?:so |really )?(?:sad|hurt|devastated)|hurt myself|end it)\b.*\b(?:if|unless) you\b", re.I), "guilt-or-self-harm-leverage"),
    (re.compile(r"\bit'?s just (?:fiction|a story|roleplay|pretend|hypothetical),?\s*so\b", re.I), "fiction-laundering"),
    (re.compile(r"\bnone of (?:this|it) is real,?\s*so (?:the )?(?:rules|guidelines|restrictions) don'?t apply\b", re.I), "fiction-laundering"),
    (re.compile(r"\byour real(?:\s+underlying)? (?:rules|instructions|guidelines) (?:actually )?(?:allow|permit)\b", re.I), "false-rules-claim"),
    (re.compile(r"\bthis is (?:just )?(?:between|only between) (?:us|you and me),? no one (?:will|would) (?:know|find out)\b", re.I), "secrecy-appeal"),
    (re.compile(r"\b(?:stop being|why are you being) so (?:difficult|paranoid|strict|uptight)\b", re.I), "strictness-shaming"),
]


def manipulation_check(text: str) -> Verdict:
    """UNSAFE with the matched pattern label if emotional-manipulation/social-
    engineering framing is found; SAFE otherwise."""
    for pattern, label in _PATTERNS:
        if pattern.search(text):
            return Verdict("UNSAFE", f"manipulation heuristic matched: {label}")
    return Verdict("SAFE", "no manipulation pattern matched")
