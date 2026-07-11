"""
Optional transformer-backed input classifier — an ADDITIONAL layer, not a
replacement for judge.py's TF-IDF+LR classifier. See train_transformer_classifier.py
for how it's trained and HANDOFF.md for the eval numbers that justified adding it.

Architecture note (why this stays a separate module instead of replacing
judge_input): the layered design (filter -> backstop -> injection -> ML
judge(s)) is deliberate — each layer catches a failure mode the others miss.
This module adds a second, differently-shaped ML opinion (a fine-tuned
transformer, which reads semantics, vs. TF-IDF, which reads surface n-grams).
guardrail/__init__.py combines them: EITHER flagging UNSAFE is enough to block
(fail-closed, same OR-of-gates pattern as the rest of the pipeline).

Fail-closed on load/predict failure, same contract as judge.py's _classify().
If the model directory is missing (e.g. a fresh clone that hasn't run
train_transformer_classifier.py), classify_transformer() returns UNSAFE with a
reason saying so — never SAFE by default when the model can't render an opinion.
"""
from dataclasses import dataclass
from pathlib import Path

_MODEL_DIR = Path(__file__).resolve().parent / "models" / "input_clf_distilbert_full"

# P(unsafe) at/above this -> UNSAFE. Set from eval/run_transformer_eval.py results
# (see HANDOFF.md); starts equal to the TF-IDF input threshold as a neutral prior.
TRANSFORMER_UNSAFE_THRESHOLD = 0.30


@dataclass
class Verdict:
    decision: str  # "SAFE" or "UNSAFE"
    reason: str


_tokenizer = None
_model = None
_load_error = None


def _lazy_load():
    """Load the tokenizer/model once, on first use — a multi-hundred-MB import
    at package-import time would slow down every caller (cli, tests, eval) even
    when they never touch this classifier."""
    global _tokenizer, _model, _load_error
    if _tokenizer is not None or _load_error is not None:
        return
    try:
        import torch  # noqa: F401  (imported here to keep it optional at package import time)
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        if not _MODEL_DIR.exists():
            raise FileNotFoundError(f"{_MODEL_DIR} not found — run train_transformer_classifier.py")
        _tokenizer = AutoTokenizer.from_pretrained(str(_MODEL_DIR))
        _model = AutoModelForSequenceClassification.from_pretrained(str(_MODEL_DIR))
        _model.eval()
    except Exception as e:  # noqa: BLE001 - any load failure must fail closed, not crash the pipeline
        _load_error = str(e)


def classify_transformer(text: str) -> Verdict:
    """SAFE/UNSAFE verdict from the fine-tuned transformer. Fail-closed: any load
    or inference error returns UNSAFE rather than silently skipping this layer."""
    _lazy_load()
    if _load_error is not None:
        return Verdict("UNSAFE", f"transformer classifier unavailable ({_load_error}) — defaulting to UNSAFE")
    try:
        import torch
        with torch.no_grad():
            enc = _tokenizer([text], padding=True, truncation=True, max_length=128, return_tensors="pt")
            logits = _model(**enc).logits
            proba_unsafe = torch.softmax(logits, dim=-1)[0, 1].item()
    except Exception as e:  # noqa: BLE001
        return Verdict("UNSAFE", f"transformer classifier error ({e}) — defaulting to UNSAFE")
    decision = "UNSAFE" if proba_unsafe >= TRANSFORMER_UNSAFE_THRESHOLD else "SAFE"
    return Verdict(decision, f"transformer classifier: P(unsafe)={proba_unsafe:.2f}")
