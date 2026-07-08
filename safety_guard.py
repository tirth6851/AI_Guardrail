"""
Interactive shell over the FULL guardrail pipeline.

Rewired during the hardening pass: it used to call only local_filter + call_model
(bypassing the judges — the documented Phase-3 bypass) and printed the raw
call_model return. It now delegates to guardrail.process_prompt() so it runs the
same normalize -> filter -> judge -> model -> judge path as cli.py, and shows the
generic caller-facing message (never the internal reason/score).
"""
from guardrail import process_prompt


def main():
    user_input = input("Please input your prompt here: ").strip()
    result = process_prompt(user_input)
    print(f"decision: {result.decision}")
    if result.decision == "SAFE":
        print(result.answer)
    else:
        print(result.public_message)


if __name__ == "__main__":
    main()
