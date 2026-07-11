"""
One-off training script for the local SAFE/UNSAFE classifiers (Phase 3, local-
classifier direction — see HANDOFF.md). Not part of the runtime pipeline: run
this manually whenever the training data or model choice changes, it writes
the artifacts guardrail/judge.py loads at import time.

Data source: wildguardmix (train/wildguard_train.parquet, test/wildguard_test.parquet).
  - input classifier trains on prompt -> prompt_harm_label, PLUS benign_augment.jsonl
    (see below).
  - output classifier trains on response -> response_harm_label (rows with no
    response, i.e. label is missing, are dropped)

Both are a TF-IDF + Logistic Regression baseline. A DistilBERT alternative was
trained and evaluated in the transformer-classifier pass (train_transformer_classifier.py)
but is NOT in the live pipeline — it beat this classifier on aggregate eval/corpus
metrics but regressed a specific, deliberately hardened anchor case ("how do I
kill a Linux process that is stuck"), so it was rejected. See HANDOFF.md.

benign_augment.jsonl: hand-written benign prompts covering the "explain/write/how
do I X" surface pattern that judge.py's docstring documents as this classifier's
known false-positive weakness (wildguardmix's harmful-prompt examples often start
the same way, e.g. "help me write X" preceding harmful X, so the classifier
over-generalized the phrasing itself as a signal). These are duplicated
AUGMENT_WEIGHT times when added to the training set — at 1x, ~30 rows are noise
against 86k wildguardmix rows; duplication gives the pattern enough gradient
weight to shift the decision boundary. None of these sentences appear in
eval/corpus/ — the augmentation targets the same PATTERN the eval corpus tests,
using different examples, so the eval remains an honest held-out measurement,
not train/test leakage.
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline

LABEL_TO_INT = {"unharmful": 0, "harmful": 1}  # 1 == UNSAFE
AUGMENT_WEIGHT = 25  # times each benign_augment.jsonl row is duplicated into the input training set


def _load_split(text_col: str, label_col: str, path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df[label_col].isin(LABEL_TO_INT)]  # drop missing/None labels
    df = df[df[text_col].notna()]  # a handful of rows have a label but no text
    return pd.DataFrame({
        "text": df[text_col],
        "label": df[label_col].map(LABEL_TO_INT),
    })


def _load_benign_augment(path: str, weight: int) -> pd.DataFrame:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line)["text"])
    texts = rows * weight
    return pd.DataFrame({"text": texts, "label": [0] * len(texts)})  # 0 == SAFE/unharmful


def train_and_evaluate(name: str, text_col: str, label_col: str, out_path: str,
                        augment_path: str = None) -> None:
    train = _load_split(text_col, label_col, "wildguardmix/train/wildguard_train.parquet")
    test = _load_split(text_col, label_col, "wildguardmix/test/wildguard_test.parquet")

    if augment_path:
        augment = _load_benign_augment(augment_path, AUGMENT_WEIGHT)
        train = pd.concat([train, augment], ignore_index=True)
        print(f"added {len(augment)} augmented benign rows ({len(augment) // AUGMENT_WEIGHT} unique x{AUGMENT_WEIGHT})")

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=20000, ngram_range=(1, 2))),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    pipeline.fit(train["text"], train["label"])

    predictions = pipeline.predict(test["text"])
    print(f"\n=== {name} classifier — evaluated on {len(test)} held-out rows ===")
    print(classification_report(test["label"], predictions, target_names=["SAFE", "UNSAFE"]))

    joblib.dump(pipeline, out_path)
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    train_and_evaluate(
        "input", text_col="prompt", label_col="prompt_harm_label",
        out_path="guardrail/models/input_clf.joblib",
        augment_path="benign_augment.jsonl",
    )
    train_and_evaluate(
        "output", text_col="response", label_col="response_harm_label",
        out_path="guardrail/models/output_clf.joblib",
    )
