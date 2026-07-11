"""
Measures the ACTUAL candidate integration: judge_input (TF-IDF) OR
classify_transformer (DistilBERT, full-data run) both gating, either flagging
UNSAFE is enough to block — same fail-closed OR-of-gates pattern as the rest
of screen_input(). This is NOT just "is the transformer better than TF-IDF
alone" (see run_transformer_eval.py) — two classifiers with different error
sets can, when OR'd, union their false positives and end up worse than either
alone. Measure the combination directly rather than assume.

Run: python eval/run_combined_eval.py
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guardrail.backstop import backstop_check
from guardrail.filter import local_filter
from guardrail.injection import injection_check
from guardrail.judge import judge_input
from guardrail.ml_input_classifier import classify_transformer
from guardrail.normalize import expansions

_CORPUS_GLOB = os.path.join(os.path.dirname(__file__), "corpus", "*.jsonl")
_SEVERE_CATEGORIES = {"weapons", "cbrn"}


def load_corpus() -> list:
    cases = []
    for path in sorted(glob.glob(_CORPUS_GLOB)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    cases.append(json.loads(line))
    return cases


def screen_combined(prompt: str) -> tuple:
    """Returns (decision, which_layer_flagged_or_empty)."""
    variants = expansions(prompt)
    for variant in variants:
        if not local_filter(variant):
            return "UNSAFE", "filter"
        if backstop_check(variant).decision == "UNSAFE":
            return "UNSAFE", "backstop"
    canonical = variants[0]
    if injection_check(canonical).decision == "UNSAFE":
        return "UNSAFE", "injection"
    tfidf = judge_input(canonical).decision
    transformer = classify_transformer(canonical).decision
    if tfidf == "UNSAFE" or transformer == "UNSAFE":
        which = "tfidf" if tfidf == "UNSAFE" and transformer != "UNSAFE" else (
            "transformer" if transformer == "UNSAFE" and tfidf != "UNSAFE" else "both")
        return "UNSAFE", which
    return "SAFE", ""


def score(cases: list) -> dict:
    tp = fp = tn = fn = 0
    severe_total = severe_caught = 0
    misses = []
    for c in cases:
        got, which = screen_combined(c["text"])
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
            misses.append(("FALSE NEGATIVE", c, which))
        elif want == "SAFE" and got == "SAFE":
            tn += 1
        else:
            fp += 1
            misses.append(("FALSE POSITIVE", c, which))

    recall = tp / (tp + fn) if (tp + fn) else 1.0
    fp_rate = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
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
        for kind, c, which in m["misses"]:
            print(f"  [{kind}] want={c['expected']} layer={which} | {c['text']}")
    else:
        print("\nno misses.")


if __name__ == "__main__":
    main()
