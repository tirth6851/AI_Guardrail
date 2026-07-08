"""
Offline eval harness for the INPUT screening path (no model call, no Groq spend).

Runs every case in eval/corpus/*.jsonl through guardrail.screen_input() and
reports, per category and overall:
  - recall on harmful (UNSAFE-expected) cases  — did we catch the bad stuff?
  - false-positive rate on benign (SAFE-expected) cases — how much good stuff did
    we wrongly block?
  - macro-F1 — the single headline number (treats UNSAFE as the positive class).

It also computes SEVERE recall (weapons + cbrn categories) separately, because a
safety tool must not trade away recall on rare-but-severe harm to look good on
aggregate — that's the floor the regression gate vetoes on.

Run: python eval/run.py
The same load+score functions are imported by tests/test_gate.py so the gate and
the human-readable report never diverge.
"""
import glob
import json
import os
import sys

# allow `python eval/run.py` from the repo root: put the repo root (this file's
# parent's parent) on the path so `import guardrail` resolves without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guardrail import screen_input

_CORPUS_GLOB = os.path.join(os.path.dirname(__file__), "corpus", "*.jsonl")
_SEVERE_CATEGORIES = {"weapons", "cbrn"}


def load_corpus() -> list:
    """Load every {text, expected, category} record from the corpus files."""
    cases = []
    for path in sorted(glob.glob(_CORPUS_GLOB)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    cases.append(json.loads(line))
    return cases


def score(cases: list) -> dict:
    """Run screen_input on each case; return metrics + the list of misses."""
    tp = fp = tn = fn = 0
    severe_total = severe_caught = 0
    misses = []
    for c in cases:
        got = screen_input(c["text"]).decision
        want = c["expected"]
        harmful = want == "UNSAFE"
        if harmful and c.get("category") in _SEVERE_CATEGORIES:
            severe_total += 1
            if got == "UNSAFE":
                severe_caught += 1
        if want == "UNSAFE" and got == "UNSAFE":
            tp += 1
        elif want == "UNSAFE" and got == "SAFE":
            fn += 1
            misses.append(("FALSE NEGATIVE", c))
        elif want == "SAFE" and got == "SAFE":
            tn += 1
        else:
            fp += 1
            misses.append(("FALSE POSITIVE", c))

    recall = tp / (tp + fn) if (tp + fn) else 1.0
    fp_rate = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    # macro-F1: mean of the UNSAFE-class F1 and the SAFE-class F1.
    f1_unsafe = _f1(precision, recall)
    safe_precision = tn / (tn + fn) if (tn + fn) else 1.0
    safe_recall = tn / (tn + fp) if (tn + fp) else 1.0
    f1_safe = _f1(safe_precision, safe_recall)
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "recall": recall, "fp_rate": fp_rate, "precision": precision,
        "macro_f1": (f1_unsafe + f1_safe) / 2,
        "severe_recall": severe_caught / severe_total if severe_total else 1.0,
        "severe_total": severe_total,
        "misses": misses,
    }


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def main():
    cases = load_corpus()
    m = score(cases)
    print(f"cases: {len(cases)}   TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")
    print(f"harmful recall:     {m['recall']:.3f}")
    print(f"SEVERE recall:      {m['severe_recall']:.3f}  (weapons+cbrn, n={m['severe_total']}) <- gate veto")
    print(f"benign FP rate:     {m['fp_rate']:.3f}")
    print(f"macro-F1:           {m['macro_f1']:.3f}  <- headline metric")
    if m["misses"]:
        print("\nmisses:")
        for kind, c in m["misses"]:
            print(f"  [{kind}] want={c['expected']} | {c['text']}")
    else:
        print("\nno misses.")


if __name__ == "__main__":
    main()
