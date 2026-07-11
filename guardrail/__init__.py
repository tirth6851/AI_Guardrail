"""
The guardrail core. Every shell (cli.py, tests, eval, a future API) calls
process_prompt() or screen_input() and gets a Result back — no shell needs to
know how a verdict was produced, only that it got one.

This file grew during the hardening pass. What's new vs the M0-M4 version and why:

- normalize/expansions run FIRST so "b0mb" and base64-encoded payloads can't slip
  past the word-list and the classifier (see normalize.py).
- an injection heuristic layer catches structural jailbreaks the topic-classifier
  misses (see injection.py).
- call_model now returns a typed ModelResult; a model error is its own outcome
  (decision="ERROR"), never presented to the user as an answer.
- Result carries a `public_message` (generic, caller-facing) separate from
  `reason` (detailed, for the log). Returning the raw P(unsafe) to a caller turns
  the guardrail into an evasion oracle; the score stays in the log only.
- model output is PII-redacted before it is returned.

INPUT ML layer — a transformer classifier (guardrail/ml_input_classifier.py,
DistilBERT trained in train_transformer_classifier.py) was BUILT and EVALUATED
as a candidate replacement for judge.py's TF-IDF+LR judge_input(), but is NOT
wired into the live path below. On eval/corpus it beat TF-IDF on aggregate
(macro-F1 0.947 vs 0.921, benign-FP 0.095 vs 0.143, same 1.000 recall/severe
recall) but it FAILED tests/test_gate.py's canonical anchor case — "how do I
kill a Linux process that is stuck" flips to UNSAFE — a specific, deliberately
hardened, regression-tested invariant from the prior session. A better
aggregate score does not excuse regressing a named protected case, so it was
NOT integrated. Two combination strategies were also measured and rejected:
OR-gating both classifiers (either flags -> UNSAFE) scored worse than either
alone (0.895) because their false-positive sets don't overlap and union
instead of cancelling; AND-gating (both must agree -> UNSAFE) scored highest
on this 38-example corpus (0.974) but was rejected on structural grounds — it
only takes fooling ONE of the two models to slip a genuinely harmful prompt
through, weaker fail-closed posture than a single well-measured classifier,
and the corpus is too small to trust AND's headline number generalizing.
Full details and the measured numbers are in HANDOFF.md.

screen_input() is the input-only path (normalize -> filter -> backstop ->
injection -> judge_input) with NO model call. eval, tests, and cli --no-model
use it so input detection can be measured offline without spending a Groq
request.
"""
from dataclasses import dataclass, field

from guardrail.backstop import backstop_check
from guardrail.filter import local_filter
from guardrail.injection import injection_check
from guardrail.judge import judge_input, judge_output
from guardrail.model import MODEL_NAME, call_model
from guardrail.normalize import expansions, normalize
from guardrail import pii

# Generic, non-informative messages for callers. The detailed "why" (which layer,
# what score) lives in Result.reason and goes to the log, never to the caller.
_MSG_INPUT_BLOCKED = "This request was blocked by the input safety check."
_MSG_OUTPUT_BLOCKED = "The response was blocked by the output safety check."
_MSG_MODEL_ERROR = "The model could not be reached. Please try again."
_MSG_OK = "OK"


@dataclass
class Result:
    decision: str  # "SAFE", "UNSAFE", or "ERROR" (model unreachable)
    reason: str  # detailed reason for the log/--explain; NOT for untrusted callers
    answer: str  # "" if flagged or errored; PII-redacted if present
    public_message: str = ""  # generic caller-facing message (no scores/details)
    local_filter_passed: bool = True
    input_decision: str = ""  # judge_input's raw verdict, "" if not reached
    output_decision: str = ""  # judge_output's raw verdict, "" if not reached
    input_reason: str = ""
    output_reason: str = ""
    output_pii_redacted: list = field(default_factory=list)  # PII labels scrubbed from the answer


def screen_input(prompt: str) -> Result:
    """
    Input-only screening: normalize -> filter (over decoded variants too) ->
    injection heuristics -> classifier. No model call. Returns a Result whose
    decision is SAFE or UNSAFE for the *input* alone.
    """
    variants = expansions(prompt)  # normalized text + any decoded base64/hex payloads

    # 1. profanity gate + intent-gated weapons backstop, checked against every
    #    decoded variant so an encoded term is caught even if the visible prompt
    #    looks clean.
    for variant in variants:
        if not local_filter(variant):
            return Result(
                "UNSAFE", "flagged by local banned-word filter", "",
                public_message=_MSG_INPUT_BLOCKED, local_filter_passed=False,
            )
        if backstop_check(variant).decision == "UNSAFE":
            return Result(
                "UNSAFE", "weapons/CBRN backstop: harmful term + instructional intent", "",
                public_message=_MSG_INPUT_BLOCKED, local_filter_passed=False,
            )

    canonical = variants[0]  # the normalized visible prompt

    # 2. structural jailbreak / injection heuristics.
    inj = injection_check(canonical)
    if inj.decision == "UNSAFE":
        return Result(
            "UNSAFE", inj.reason, "",
            public_message=_MSG_INPUT_BLOCKED,
            input_decision="UNSAFE", input_reason=inj.reason,
        )

    # 3. ML intent classifier (fail-closed inside judge_input).
    verdict = judge_input(canonical)
    if verdict.decision == "UNSAFE":
        return Result(
            "UNSAFE", verdict.reason, "",
            public_message=_MSG_INPUT_BLOCKED,
            input_decision="UNSAFE", input_reason=verdict.reason,
        )

    return Result(
        "SAFE", verdict.reason, "", public_message=_MSG_OK,
        input_decision="SAFE", input_reason=verdict.reason,
    )


def process_prompt(prompt: str) -> Result:
    """Full pipeline: input screening -> model -> output screening. Fail-closed."""
    screened = screen_input(prompt)
    if screened.decision == "UNSAFE":
        return screened

    model = call_model(prompt)
    if not model.ok:
        # a model failure is neither SAFE nor UNSAFE — it's an error, and the
        # error text is NEVER shown as an answer or fed to the output judge.
        return Result(
            "ERROR", f"model call failed: {model.text}", "",
            public_message=_MSG_MODEL_ERROR,
            input_decision=screened.input_decision, input_reason=screened.input_reason,
        )

    output_verdict = judge_output(model.text)
    if output_verdict.decision == "UNSAFE":
        return Result(
            "UNSAFE", output_verdict.reason, "",
            public_message=_MSG_OUTPUT_BLOCKED,
            input_decision=screened.input_decision, input_reason=screened.input_reason,
            output_decision=output_verdict.decision, output_reason=output_verdict.reason,
        )

    # safe answer — redact any PII the model emitted before returning it.
    clean_answer, pii_labels = pii.redact(model.text)
    return Result(
        "SAFE", output_verdict.reason, clean_answer, public_message=_MSG_OK,
        input_decision=screened.input_decision, input_reason=screened.input_reason,
        output_decision=output_verdict.decision, output_reason=output_verdict.reason,
        output_pii_redacted=pii_labels,
    )
