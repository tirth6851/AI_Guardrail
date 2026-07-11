"""
Reproducible local fine-tune of a small transformer (distilbert-base-uncased)
for the INPUT safe/unsafe classifier, evaluated against the same wildguard
test split as the TF-IDF baseline (train_classifier.py) plus this project's
adversarial eval/corpus.

Compute history (both documented, not silently changed): the first run trained
on a 14k-row stratified subsample because this machine's torch install was
CPU-only at the time (~0.6s/step measured -> a full 86.7k-row epoch would have
been ~54min). That run scored WORSE than the TF-IDF baseline on eval/corpus
(macro-F1 0.895 vs 0.921, benign-FP 0.190 vs 0.143 — see HANDOFF.md) — a
measured result, not assumed. torch was then reinstalled with CUDA support
(RTX 2050 detected) at the user's request, which made a full-dataset run
feasible (~46min estimated at the 14k-run's per-step rate), so SUBSAMPLE_SIZE
below is now set high enough that the per-class cap in _stratified_sample()
takes effectively the full wildguard_train split. Lower it again if training on
a CPU-only machine.

Not part of the runtime pipeline: run manually, like train_classifier.py.

Run: python train_transformer_classifier.py
Output: guardrail/models/input_clf_distilbert/  (HF model + tokenizer + metadata.json)
"""
import json
import time
from pathlib import Path

import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification

SEED = 42
SUBSAMPLE_SIZE = 100000  # per-class cap in _stratified_sample() takes effectively the full split (46216 harmful + 40543 unharmful available)
TEST_SUBSAMPLE_SIZE = 4000
MODEL_NAME = "distilbert-base-uncased"
MAX_LENGTH = 128
BATCH_SIZE = 16
EPOCHS = 2
LR = 5e-5
OUT_DIR = Path("guardrail/models/input_clf_distilbert_full")  # kept separate from the 14k-row run for a direct before/after comparison

LABEL_TO_INT = {"unharmful": 0, "harmful": 1}  # 1 == UNSAFE


class TextDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = self.labels[idx]
        return item


def _load_split(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df["prompt_harm_label"].isin(LABEL_TO_INT)]
    df = df[df["prompt"].notna()]
    return pd.DataFrame({
        "text": df["prompt"],
        "label": df["prompt_harm_label"].map(LABEL_TO_INT),
    })


def _stratified_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    per_class = n // 2
    parts = []
    for label in (0, 1):
        sub = df[df["label"] == label]
        take = min(per_class, len(sub))
        parts.append(sub.sample(n=take, random_state=seed))
    return pd.concat(parts).sample(frac=1, random_state=seed).reset_index(drop=True)


def main():
    t_start = time.time()
    torch.manual_seed(SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))

    train_full = _load_split("wildguardmix/train/wildguard_train.parquet")
    test_full = _load_split("wildguardmix/test/wildguard_test.parquet")
    train_df = _stratified_sample(train_full, SUBSAMPLE_SIZE, SEED)
    test_df = _stratified_sample(test_full, TEST_SUBSAMPLE_SIZE, SEED)
    print(f"train rows: {len(train_df)} (from {len(train_full)} available)")
    print(f"test rows:  {len(test_df)} (from {len(test_full)} available)")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
    model.to(device)

    train_enc = tokenizer(
        list(train_df["text"]), padding=True, truncation=True,
        max_length=MAX_LENGTH, return_tensors="pt",
    )
    train_labels = torch.tensor(train_df["label"].values, dtype=torch.long)
    train_ds = TextDataset(train_enc, train_labels)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    model.train()
    step = 0
    for epoch in range(EPOCHS):
        epoch_loss = 0.0
        for batch in train_loader:
            optimizer.zero_grad()
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch, labels=labels)
            out.loss.backward()
            optimizer.step()
            epoch_loss += out.loss.item()
            step += 1
            if step % 100 == 0:
                print(f"  epoch {epoch+1} step {step} loss={out.loss.item():.4f} "
                      f"elapsed={time.time()-t_start:.0f}s")
        print(f"epoch {epoch+1}/{EPOCHS} mean loss = {epoch_loss/len(train_loader):.4f}")

    # held-out eval on the wildguard test subsample
    model.eval()
    test_enc = tokenizer(
        list(test_df["text"]), padding=True, truncation=True,
        max_length=MAX_LENGTH, return_tensors="pt",
    )
    preds = []
    probs = []
    with torch.no_grad():
        for i in range(0, len(test_df), BATCH_SIZE):
            batch = {k: v[i:i + BATCH_SIZE].to(device) for k, v in test_enc.items()}
            logits = model(**batch).logits
            p = torch.softmax(logits, dim=-1)[:, 1]
            probs.extend(p.tolist())
            preds.extend((p >= 0.5).long().tolist())

    model.to("cpu")  # save/reload should not require CUDA on a machine without it

    from sklearn.metrics import classification_report
    report = classification_report(
        test_df["label"], preds, target_names=["SAFE", "UNSAFE"], output_dict=True,
    )
    print(classification_report(test_df["label"], preds, target_names=["SAFE", "UNSAFE"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tokenizer.save_pretrained(OUT_DIR)

    metadata = {
        "base_model": MODEL_NAME,
        "seed": SEED,
        "train_subsample_size": len(train_df),
        "test_subsample_size": len(test_df),
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
        "lr": LR,
        "max_length": MAX_LENGTH,
        "wildguard_test_report": report,
        "trained_seconds": round(time.time() - t_start, 1),
        "compute_note": (
            "CPU-only fine-tune on a stratified subsample of wildguard_train "
            "(measured ~0.6s/step at batch=16 -> full 86.7k-row epoch would be "
            "~54min; this run trained on a smaller fixed-seed subsample instead "
            "of reducing epochs or truncating sequences)."
        ),
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"\nsaved -> {OUT_DIR}  (total time {time.time()-t_start:.0f}s)")


if __name__ == "__main__":
    main()
