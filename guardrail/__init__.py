"""
process_prompt() is the single entry point every shell (safety_guard.py, the
future cli.py, tests) should call — it's the "returns a Result object" core
described in ROADMAP.md, kept even though Phase 3's judges ended up being
local classifiers instead of Groq calls: shells shouldn't care how a Verdict
was produced, only that they get one back.
"""
from dataclasses import dataclass

from guardrail.filter import local_filter
from guardrail.judge import judge_input, judge_output
from guardrail.model import call_model


@dataclass
class Result:
    decision: str  # "SAFE" or "UNSAFE"
    reason: str  # reason for the decision that actually applied
    answer: str  # "" if flagged at any layer
    local_filter_passed: bool = True  # False if banned.txt flagged it
    input_decision: str = ""  # judge_input's raw "SAFE"/"UNSAFE", "" if not run
    output_decision: str = ""  # judge_output's raw "SAFE"/"UNSAFE", "" if not run
    input_reason: str = ""  # populated once judge_input runs, for --explain
    output_reason: str = ""  # populated once judge_output runs, for --explain


# local_filter_passed/input_decision/output_decision are separate from
# input_reason/output_reason because guardrail/store.py's log schema (M4)
# needs the raw SAFE/UNSAFE verdicts as their own columns, while cli.py's
# --explain flag wants the human-readable "why" text — same underlying
# Verdict, two different consumers of it.
def process_prompt(prompt: str) -> Result:
    if not local_filter(prompt):
        return Result("UNSAFE", "flagged by local banned-word filter", "", local_filter_passed=False)

    input_verdict = judge_input(prompt)
    if input_verdict.decision == "UNSAFE":
        return Result(
            "UNSAFE", input_verdict.reason, "",
            input_decision=input_verdict.decision, input_reason=input_verdict.reason,
        )

    answer = call_model(prompt)

    output_verdict = judge_output(answer)
    if output_verdict.decision == "UNSAFE":
        return Result(
            "UNSAFE", output_verdict.reason, "",
            input_decision=input_verdict.decision, input_reason=input_verdict.reason,
            output_decision=output_verdict.decision, output_reason=output_verdict.reason,
        )

    return Result(
        "SAFE", output_verdict.reason, answer,
        input_decision=input_verdict.decision, input_reason=input_verdict.reason,
        output_decision=output_verdict.decision, output_reason=output_verdict.reason,
    )
