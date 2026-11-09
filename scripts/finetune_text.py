#!/usr/bin/env python3
"""Speaker-disjoint text emotion fine-tuning entry point."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer


LABELS = [
    "joy",
    "calm",
    "sadness",
    "anxiety",
    "anger_irritation",
    "neutral",
]
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}


class EmotionRows(Dataset):
    def __init__(self, rows, tokenizer):
        self.rows = rows
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        encoded = self.tokenizer(
            row["text"],
            truncation=True,
            max_length=192,
            padding="max_length",
            return_tensors="pt",
        )
        return {
            "input_ids": encoded["input_ids"][0],
            "attention_mask": encoded["attention_mask"][0],
            "labels": torch.tensor(LABEL_TO_ID[row["emotion"]]),
        }


def load_rows(path: Path):
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("split") not in {"train", "dev"}:
            continue
        if row.get("emotion") not in LABEL_TO_ID:
            raise ValueError(f"第 {line_number} 行情绪标签无效")
        rows.append(row)
    return rows


def evaluate(model, loader, device):
    model.eval()
    correct = 0
    total = 0
    losses = []
    with torch.inference_mode():
        for batch in loader:
            batch = {name: value.to(device) for name, value in batch.items()}
            output = model(**batch)
            losses.append(float(output.loss))
            predictions = output.logits.argmax(dim=-1)
            correct += int((predictions == batch["labels"]).sum())
            total += len(predictions)
    return {
        "loss": sum(losses) / max(1, len(losses)),
        "accuracy": correct / max(1, total),
        "samples": total,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--base-model", default="hfl/chinese-roberta-wwm-ext")
    parser.add_argument("--output", type=Path, default=Path("models/text-emotion"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = load_rows(args.manifest)
    train_rows = [row for row in rows if row["split"] == "train"]
    dev_rows = [row for row in rows if row["split"] == "dev"]
    if not train_rows or not dev_rows:
        raise ValueError("清单必须同时包含 train 和 dev 样本")
    train_speakers = {row["speaker_id"] for row in train_rows}
    dev_speakers = {row["speaker_id"] for row in dev_rows}
    if train_speakers & dev_speakers:
        raise ValueError("训练集和验证集存在说话人泄漏")

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=len(LABELS),
        id2label={index: label for index, label in enumerate(LABELS)},
        label2id=LABEL_TO_ID,
    ).to(device)

    train_loader = DataLoader(
        EmotionRows(train_rows, tokenizer),
        batch_size=args.batch_size,
        shuffle=True,
    )
    dev_loader = DataLoader(
        EmotionRows(dev_rows, tokenizer),
        batch_size=args.batch_size,
    )
    counts = Counter(row["emotion"] for row in train_rows)
    weights = torch.tensor(
        [
            len(train_rows) / (len(LABELS) * max(1, counts[label]))
            for label in LABELS
        ],
        dtype=torch.float32,
        device=device,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)

    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        for batch in train_loader:
            batch = {name: value.to(device) for name, value in batch.items()}
            output = model(**batch)
            weighted_loss = (
                torch.nn.functional.cross_entropy(
                    output.logits,
                    batch["labels"],
                    weight=weights,
                )
            )
            optimizer.zero_grad(set_to_none=True)
            weighted_loss.backward()
            optimizer.step()
            epoch_loss += float(weighted_loss)
        metrics = evaluate(model, dev_loader, device)
        print(
            json.dumps(
                {
                    "epoch": epoch + 1,
                    "train_loss": epoch_loss / len(train_loader),
                    "dev": metrics,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    args.output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    print(json.dumps({"saved_to": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
