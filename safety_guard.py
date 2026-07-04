"""
Phase 1 (local filter) and Phase 2 (Groq call) logic now live in the
guardrail/ package as plain functions (guardrail/filter.py, guardrail/model.py).
This script is just the original interactive shell, rewired to call them
instead of duplicating the logic with a global.
"""
from guardrail.filter import local_filter
from guardrail.model import call_model


def main():
  user_input = input("Please input your prompt here:").strip()
  if not local_filter(user_input):
    print("FLAGGED: Prompt is illegal")
    return
  print("sending it to LLM")
  print(call_model(user_input))


if __name__ == "__main__":
  main()



