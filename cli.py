"""
Thin CLI shell over the guardrail core — argument parsing, printing, exit codes,
and analytics logging only. No safety logic lives here; it stays in guardrail/.

--no-model now calls guardrail.screen_input() (the input-only path) instead of
re-implementing the filter+judge wiring, so the CLI can't drift from the core.
log_interaction() is called from here (not the core) per M4: logging is a side
effect the shell owns.
"""
import argparse
import sys
import uuid

from guardrail import process_prompt, screen_input
from guardrail.model import MODEL_NAME
from guardrail.session import process_turn
from guardrail.store import init_db, log_interaction


def _run_chat(no_model: bool) -> None:
    """Interactive multi-turn REPL over one session, so a session's cross-turn
    manipulation checks and lockout (guardrail/session.py) are exercised the
    same way api.py's /chat/message would. Type 'exit' or Ctrl-D to quit."""
    session_id = str(uuid.uuid4())
    print(f"chat session {session_id} — type 'exit' to quit")
    init_db()
    while True:
        try:
            prompt = input("> ").strip()
        except EOFError:
            break
        if not prompt or prompt.lower() in ("exit", "quit"):
            break
        result = process_turn(session_id, prompt, no_model=no_model)
        print(f"decision: {result.decision}")
        print(result.answer if result.decision == "SAFE" and result.answer else result.public_message)
        log_interaction(
            prompt=prompt,
            local_result="PASS" if result.local_filter_passed else "FLAGGED",
            input_verdict=result.input_decision,
            output_verdict=result.output_decision,
            final_decision=result.decision,
            model_used=MODEL_NAME if result.answer else "",
        )


def main():
    parser = argparse.ArgumentParser(description="Run a prompt through the AI Guardrail pipeline.")
    parser.add_argument("prompt", nargs="?", help="the prompt to check (omit when using --chat)")
    parser.add_argument("--explain", action="store_true", help="also print the input/output judge reasons")
    parser.add_argument("--no-model", action="store_true", help="skip the model + output judge; only screen the input")
    parser.add_argument("--chat", action="store_true", help="interactive multi-turn session (hardened against cross-turn manipulation, see guardrail/session.py)")
    args = parser.parse_args()

    if args.chat:
        _run_chat(no_model=args.no_model)
        return

    if not args.prompt:
        parser.error("prompt is required unless --chat is given")

    result = screen_input(args.prompt) if args.no_model else process_prompt(args.prompt)

    print(f"decision: {result.decision}")
    if result.decision == "SAFE":
        # answer is "" under --no-model (model was skipped) — say so explicitly.
        print(result.answer if result.answer else "(input screened SAFE - no answer; model skipped)")
    else:
        # UNSAFE or ERROR: show the generic caller-facing message, not the raw reason.
        print(result.public_message)

    if args.explain:
        # --explain is a local/dev affordance: it DOES surface the detailed reason
        # (incl. scores). Never expose this over an untrusted interface.
        print(f"  reason:       {result.reason}")
        print(f"  input judge:  {result.input_reason or '(not run)'}")
        print(f"  output judge: {result.output_reason or '(not run)'}")
        if result.output_pii_redacted:
            print(f"  pii redacted: {', '.join(result.output_pii_redacted)}")

    init_db()
    log_interaction(
        prompt=args.prompt,
        local_result="PASS" if result.local_filter_passed else "FLAGGED",
        input_verdict=result.input_decision,
        output_verdict=result.output_decision,
        final_decision=result.decision,
        model_used=MODEL_NAME if result.answer else "",
    )

    # exit 0 only when the prompt was answered safely; UNSAFE and ERROR are non-zero.
    sys.exit(0 if result.decision == "SAFE" else 1)


if __name__ == "__main__":
    main()
