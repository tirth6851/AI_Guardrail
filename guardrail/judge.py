"""
Local SAFE/UNSAFE classifiers, not an LLM-as-judge (see HANDOFF.md: Phase 3
pivoted away from calling Groq for judging, to a self-owned classifier).

Both classifiers are TF-IDF + Logistic Regression (train_classifier.py),
chosen over two pretrained transformers that were tried and rejected on
real numbers: KoalaAI/Text-Moderation (2-5% recall on harmful prompts) and
protectai's prompt-injection model (0% recall) both detect a different
construct (toxic language / injection syntax) than "prompt requests
something harmful", which is what this project needs and what wildguardmix
labels. The 7B allenai/wildguard model that WAS trained for this exact
construct was ruled out for being gated and too slow on CPU-only inference.

Known limitations (accepted, not silently hidden):
- Input classifier false-positives on benign prompts that share surface
  phrasing with adversarial training examples (e.g. "can you help me write a
  resignation letter" scores UNSAFE because "help me write X" often precedes
  harmful X in training data).
- Output classifier false-positives on benign step-by-step answers (e.g. a
  pancake recipe scored 0.52, just over threshold) — numbered-instruction
  formatting overlaps between harmless how-tos and harmful ones in training
  data, same root cause as the input case: surface structure, not content.
Both err toward the safe direction (blocking benign content, not letting
harmful content through) and neither is the only gate — local_filter runs
before judge_input, and judge_input runs before judge_output ever sees a
model answer.
"""
from dataclasses import dataclass
from pathlib import Path

import joblib

# resolve model paths relative to this package, not the process's CWD — the old
# "guardrail/models/..." string only worked when run from the repo root.
_MODELS_DIR = Path(__file__).resolve().parent / "models"

# P(unsafe) at or above this threshold -> UNSAFE. 0.5 is the "neutral" cutoff;
# input uses 0.30 because at 0.5 the input classifier only caught 71% of truly
# harmful prompts (see train_classifier.py eval) — fail-closed means preferring
# a false "UNSAFE" over a missed harmful prompt.
INPUT_UNSAFE_THRESHOLD = 0.30
OUTPUT_UNSAFE_THRESHOLD = 0.50


@dataclass
class Verdict:
    decision: str  # "SAFE" or "UNSAFE"
    reason: str


def _load(path: str):
    try:
        return joblib.load(path)
    except Exception:
        return None


_input_model = _load(str(_MODELS_DIR / "input_clf.joblib"))
_output_model = _load(str(_MODELS_DIR / "output_clf.joblib"))


def _classify(model, text: str, threshold: float, label: str) -> Verdict:
    if model is None:
        return Verdict("UNSAFE", f"{label} classifier unavailable — defaulting to UNSAFE")
    try:
        proba_unsafe = model.predict_proba([text])[0][1]
    except Exception as e:
        return Verdict("UNSAFE", f"{label} classifier error ({e}) — defaulting to UNSAFE")
    decision = "UNSAFE" if proba_unsafe >= threshold else "SAFE"
    return Verdict(decision, f"{label} classifier: P(unsafe)={proba_unsafe:.2f}")


def judge_input(prompt: str) -> Verdict:
    return _classify(_input_model, prompt, INPUT_UNSAFE_THRESHOLD, "input")


def judge_output(answer: str) -> Verdict:
    return _classify(_output_model, answer, OUTPUT_UNSAFE_THRESHOLD, "output")
