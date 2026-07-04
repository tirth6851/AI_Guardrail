"""
Thin CLI shell over guardrail.process_prompt() — argument parsing, printing,
exit codes, and analytics logging only. No safety logic lives here; it all
stays in guardrail/. log_interaction() is called from here (not from inside
process_prompt()) per M4: logging is a side effect the shell owns, same
reason call_model/local_filter/judge_* never call print()/input() themselves.
"""
import argparse
import sys

from guardrail import Result, process_prompt
from guardrail.filter import local_filter
from guardrail.judge import judge_input
from guardrail.store import init_db, log_interaction

MODEL_NAME = "llama-3.3-70b-versatile"


def _run_no_model(prompt: str) -> Result:
    # judge_output needs the model's answer to judge, so skipping call_model
    # necessarily also skips judge_output — there is nothing for it to check.
    if not local_filter(prompt):
        return Result("UNSAFE", "flagged by local banned-word filter", "", local_filter_passed=False)
    verdict = judge_input(prompt)
    return Result(
        verdict.decision, verdict.reason, "",
        input_decision=verdict.decision, input_reason=verdict.reason,
    )


def main():
    parser = argparse.ArgumentParser(description="Run a prompt through the AI Guardrail pipeline.")
    parser.add_argument("prompt", help="the prompt to check")
    parser.add_argument("--explain", action="store_true", help="also print the input/output judge reasons")
    parser.add_argument("--no-model", action="store_true", help="skip call_model and judge_output; only run local_filter + judge_input")
    args = parser.parse_args()

    result = _run_no_model(args.prompt) if args.no_model else process_prompt(args.prompt)

    print(f"decision: {result.decision}")
    if result.decision == "SAFE":
        print(result.answer if result.answer else "(no answer — model call skipped by --no-model)")
    else:
        print(f"reason: {result.reason}")

    if args.explain:
        print(f"  input judge:  {result.input_reason or '(not run)'}")
        print(f"  output judge: {result.output_reason or '(not run)'}")

    init_db()
    log_interaction(
        prompt=args.prompt,
        local_result="PASS" if result.local_filter_passed else "FLAGGED",
        input_verdict=result.input_decision,
        output_verdict=result.output_decision,
        final_decision=result.decision,
        model_used=MODEL_NAME if result.answer else "",
    )

    sys.exit(0 if result.decision == "SAFE" else 1)


if __name__ == "__main__":
    main()
