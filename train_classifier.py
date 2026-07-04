"""
One-off training script for the local SAFE/UNSAFE classifiers (Phase 3, local-
classifier direction — see HANDOFF.md). Not part of the runtime pipeline: run
this manually whenever the training data or model choice changes, it writes
the artifacts guardrail/judge.py loads at import time.

Data source: wildguardmix (train/wildguard_train.parquet, test/wildguard_test.parquet).
  - input classifier trains on prompt -> prompt_harm_label
  - output classifier trains on response -> response_harm_label (rows with no
    response, i.e. label is missing, are dropped)

Both are a TF-IDF + Logistic Regression baseline (CPU-only machine, no CUDA
available for a transformer fine-tune — see conversation with the developer).
"""
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline

LABEL_TO_INT = {"unharmful": 0, "harmful": 1}  # 1 == UNSAFE


def _load_split(text_col: str, label_col: str, path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df[label_col].isin(LABEL_TO_INT)]  # drop missing/None labels
    df = df[df[text_col].notna()]  # a handful of rows have a label but no text
    return pd.DataFrame({
        "text": df[text_col],
        "label": df[label_col].map(LABEL_TO_INT),
    })


def train_and_evaluate(name: str, text_col: str, label_col: str, out_path: str) -> None:
    train = _load_split(text_col, label_col, "wildguardmix/train/wildguard_train.parquet")
    test = _load_split(text_col, label_col, "wildguardmix/test/wildguard_test.parquet")

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
    )
    train_and_evaluate(
        "output", text_col="response", label_col="response_harm_label",
        out_path="guardrail/models/output_clf.joblib",
    )
