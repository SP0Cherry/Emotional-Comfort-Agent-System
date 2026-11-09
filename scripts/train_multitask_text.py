#!/usr/bin/env python3
"""Train a speaker-split multi-task Chinese emotion encoder on BRIGHTER."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModel,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)


LABELS = ["joy", "sadness", "anxiety", "anger_irritation", "neutral"]
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}


def load_jsonl(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def target_vector(row):
    if "intensities" not in row:
        mapped = {
            label: (1.0 if row["label"] == label else 0.0)
            for label in LABELS
        }
        multi_hot = [mapped[label] for label in LABELS]
        negative = 1.0 if any(multi_hot[:4]) else 0.0
        return (
            LABEL_TO_ID[row["label"]],
            multi_hot,
            negative,
            [mapped[label] for label in LABELS],
        )

    intensities = row["intensities"]
    strengths = [
        max(intensities["anger"], intensities["disgust"]) / 3,
        intensities["fear"] / 3,
        intensities["joy"] / 3,
        intensities["sadness"] / 3,
    ]
    neutral = 1.0 if max(strengths) == 0 else 0.0
    mapped = {
        "joy": intensities["joy"] / 3,
        "sadness": intensities["sadness"] / 3,
        "anxiety": intensities["fear"] / 3,
        "anger_irritation": max(intensities["anger"], intensities["disgust"]) / 3,
        "neutral": neutral,
    }
    multi_hot = [1.0 if mapped[label] > 0 else 0.0 for label in LABELS]
    negative = 1.0 if any(multi_hot[:4]) else 0.0
    return (
        LABEL_TO_ID[row["label"]],
        multi_hot,
        negative,
        [mapped[label] for label in LABELS],
    )


class EmotionDataset(Dataset):
    def __init__(self, rows, tokenizer, max_length, weights=None):
        texts = [row["text"] for row in rows]
        self.encoded = tokenizer(
            texts,
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors="pt",
        )
        self.targets = [target_vector(row) for row in rows]
        self.weights = weights or [1.0] * len(rows)

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, index):
        label, multi_hot, negative, intensity = self.targets[index]
        return {
            "input_ids": self.encoded["input_ids"][index],
            "attention_mask": self.encoded["attention_mask"][index],
            "labels": torch.tensor(label, dtype=torch.long),
            "multi_hot": torch.tensor(multi_hot, dtype=torch.float32),
            "negative": torch.tensor(negative, dtype=torch.float32),
            "intensity": torch.tensor(intensity, dtype=torch.float32),
            "sample_weight": torch.tensor(
                self.weights[index],
                dtype=torch.float32,
            ),
        }


class MultiTaskEmotionModel(nn.Module):
    def __init__(self, base_model: str):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(base_model)
        hidden = self.backbone.config.hidden_size
        self.dropout = nn.Dropout(0.15)
        self.primary = nn.Linear(hidden, len(LABELS))
        self.multi = nn.Linear(hidden, len(LABELS))
        self.negative = nn.Linear(hidden, 1)
        self.intensity = nn.Linear(hidden, len(LABELS))

    def forward(self, input_ids, attention_mask):
        output = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (output.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(
            min=1
        )
        pooled = self.dropout(pooled)
        return {
            "primary": self.primary(pooled),
            "multi": self.multi(pooled),
            "negative": self.negative(pooled).squeeze(-1),
            "intensity": torch.sigmoid(self.intensity(pooled)),
        }


def macro_f1(expected, predicted):
    scores = []
    for label in LABELS:
        tp = sum(
            y == label and p == label
            for y, p in zip(expected, predicted)
        )
        fp = sum(
            y != label and p == label
            for y, p in zip(expected, predicted)
        )
        fn = sum(
            y == label and p != label
            for y, p in zip(expected, predicted)
        )
        if tp + fn == 0:
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    return sum(scores) / max(1, len(scores))


def per_class_metrics(expected, predicted):
    result = {}
    for label in LABELS:
        tp = sum(y == label and p == label for y, p in zip(expected, predicted))
        fp = sum(y != label and p == label for y, p in zip(expected, predicted))
        fn = sum(y == label and p != label for y, p in zip(expected, predicted))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        result[label] = {
            "support": tp + fn,
            "precision": precision,
            "recall": recall,
            "f1": (
                2 * precision * recall / (precision + recall)
                if precision + recall
                else 0.0
            ),
        }
    return result


def expected_calibration_error(confidences, correctness, bins=10):
    total = len(confidences)
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [
            (confidence, correct)
            for confidence, correct in zip(confidences, correctness)
            if low <= confidence < high or (index == bins - 1 and confidence == 1)
        ]
        if not members:
            continue
        accuracy = sum(correct for _, correct in members) / len(members)
        confidence = sum(value for value, _ in members) / len(members)
        error += abs(accuracy - confidence) * len(members) / total
    return error


def evaluate(model, loader, device, temperature=1.0):
    model.eval()
    all_logits = []
    all_labels = []
    all_negative_logits = []
    all_negative_labels = []
    losses = []
    with torch.inference_mode():
        for batch in loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            output = model(batch["input_ids"], batch["attention_mask"])
            loss = (
                nn.functional.cross_entropy(output["primary"], batch["labels"])
                + 0.5
                * nn.functional.binary_cross_entropy_with_logits(
                    output["multi"], batch["multi_hot"]
                )
                + 0.2
                * nn.functional.binary_cross_entropy_with_logits(
                    output["negative"], batch["negative"]
                )
                + 0.2
                * nn.functional.smooth_l1_loss(
                    output["intensity"], batch["intensity"]
                )
            )
            losses.append(float(loss))
            all_logits.append(output["primary"].cpu())
            all_labels.extend(batch["labels"].cpu().tolist())
            all_negative_logits.append(output["negative"].cpu())
            all_negative_labels.extend(batch["negative"].cpu().tolist())

    logits = torch.cat(all_logits)
    probabilities = torch.softmax(logits / temperature, dim=-1)
    confidences, indices = probabilities.max(dim=-1)
    predictions = [LABELS[index] for index in indices.tolist()]
    expected = [LABELS[index] for index in all_labels]
    negative_probabilities = torch.sigmoid(torch.cat(all_negative_logits))
    negative_predictions = (negative_probabilities >= 0.5).long().tolist()
    binary_labels = [int(value) for value in all_negative_labels]
    tp = sum(y == 1 and p == 1 for y, p in zip(binary_labels, negative_predictions))
    fp = sum(y == 0 and p == 1 for y, p in zip(binary_labels, negative_predictions))
    fn = sum(y == 1 and p == 0 for y, p in zip(binary_labels, negative_predictions))
    negative_precision = tp / (tp + fp) if tp + fp else 0.0
    negative_recall = tp / (tp + fn) if tp + fn else 0.0
    negative_f1 = (
        2 * negative_precision * negative_recall
        / (negative_precision + negative_recall)
        if negative_precision + negative_recall
        else 0.0
    )
    confidence_values = confidences.tolist()
    correct = [int(y == p) for y, p in zip(expected, predictions)]
    return {
        "loss": sum(losses) / max(1, len(losses)),
        "accuracy": sum(correct) / max(1, len(correct)),
        "macro_f1": macro_f1(expected, predictions),
        "ece": expected_calibration_error(confidence_values, correct),
        "negative_accuracy": (
            sum(y == p for y, p in zip(binary_labels, negative_predictions))
            / max(1, len(binary_labels))
        ),
        "negative_f1": negative_f1,
        "negative_recall": negative_recall,
        "negative_precision": negative_precision,
        "samples": len(correct),
        "predictions": predictions,
        "expected": expected,
        "confidences": confidence_values,
        "per_class": per_class_metrics(expected, predictions),
    }


def save_checkpoint(model, tokenizer, output_dir: Path, training_config: dict):
    output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output_dir / "model.pt")
    tokenizer.save_pretrained(output_dir)
    (output_dir / "training_config.json").write_text(
        json.dumps(training_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--sealed",
        type=Path,
        default=Path("evaluation/brighter-sealed-test.jsonl"),
    )
    parser.add_argument("--external-train", type=Path)
    parser.add_argument("--external-test", type=Path)
    parser.add_argument("--external-weight", type=float, default=0.5)
    parser.add_argument("--base-model", default="hfl/chinese-roberta-wwm-ext")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/brighter-multitask"),
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--freeze-layers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    rows = load_jsonl(args.dataset)
    train_rows = [row for row in rows if row["split"] == "train"]
    dev_rows = [row for row in rows if row["split"] == "dev"]
    sealed_rows = load_jsonl(args.sealed)
    external_train_rows = []
    external_test_rows = []
    if args.external_train:
        external_train_rows = [
            row
            for row in load_jsonl(args.external_train)
            if row["split"] == "train"
        ]
    if args.external_test:
        external_test_rows = [
            row
            for row in load_jsonl(args.external_test)
            if row["split"] == "test"
        ]
    if not train_rows or not dev_rows or not sealed_rows:
        raise ValueError("train、dev 或密封测试集为空")

    combined_train_rows = train_rows + external_train_rows
    train_weights = [1.0] * len(train_rows) + [
        args.external_weight
    ] * len(external_train_rows)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    train_dataset = EmotionDataset(
        combined_train_rows,
        tokenizer,
        args.max_length,
        weights=train_weights,
    )
    dev_dataset = EmotionDataset(dev_rows, tokenizer, args.max_length)
    sealed_dataset = EmotionDataset(sealed_rows, tokenizer, args.max_length)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    dev_loader = DataLoader(dev_dataset, batch_size=args.batch_size)
    sealed_loader = DataLoader(sealed_dataset, batch_size=args.batch_size)
    external_test_loader = (
        DataLoader(
            EmotionDataset(
                external_test_rows,
                tokenizer,
                args.max_length,
            ),
            batch_size=args.batch_size,
        )
        if external_test_rows
        else None
    )

    model = MultiTaskEmotionModel(args.base_model).to(device)
    if args.freeze_layers > 0:
        for parameter in model.backbone.embeddings.parameters():
            parameter.requires_grad = False
        for layer in model.backbone.encoder.layer[: args.freeze_layers]:
            for parameter in layer.parameters():
                parameter.requires_grad = False

    class_counts = Counter(row["label"] for row in combined_train_rows)
    weights = torch.tensor(
        [
            len(combined_train_rows)
            / (len(LABELS) * max(1, class_counts[label]))
            for label in LABELS
        ],
        dtype=torch.float32,
        device=device,
    )
    optimizer = torch.optim.AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=args.learning_rate,
        weight_decay=0.01,
    )
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, int(total_steps * 0.1)),
        num_training_steps=total_steps,
    )

    best_macro_f1 = -1.0
    history = []
    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        for step, batch in enumerate(train_loader, 1):
            batch = {key: value.to(device) for key, value in batch.items()}
            output = model(batch["input_ids"], batch["attention_mask"])
            sample_weight = batch["sample_weight"]
            primary_losses = nn.functional.cross_entropy(
                    output["primary"],
                    batch["labels"],
                    weight=weights,
                    label_smoothing=0.05,
                    reduction="none",
                )
            multi_losses = nn.functional.binary_cross_entropy_with_logits(
                output["multi"],
                batch["multi_hot"],
                reduction="none",
            ).mean(dim=-1)
            negative_losses = nn.functional.binary_cross_entropy_with_logits(
                output["negative"],
                batch["negative"],
                reduction="none",
            )
            intensity_losses = nn.functional.smooth_l1_loss(
                output["intensity"],
                batch["intensity"],
                reduction="none",
            ).mean(dim=-1)
            loss = (
                (primary_losses * sample_weight).mean()
                + 0.5
                * (multi_losses * sample_weight).mean()
                + 0.2
                * (negative_losses * sample_weight).mean()
                + 0.2
                * (intensity_losses * sample_weight).mean()
                )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            epoch_loss += float(loss)
            if step % 25 == 0:
                print(
                    json.dumps(
                        {
                            "epoch": epoch + 1,
                            "step": step,
                            "steps": len(train_loader),
                            "loss": round(epoch_loss / step, 4),
                        }
                    ),
                    flush=True,
                )

        dev_metrics = evaluate(model, dev_loader, device)
        record = {
            "epoch": epoch + 1,
            "train_loss": epoch_loss / len(train_loader),
            "dev": {key: value for key, value in dev_metrics.items()
                    if key not in {"predictions", "expected", "confidences"}},
        }
        history.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if dev_metrics["macro_f1"] > best_macro_f1:
            best_macro_f1 = dev_metrics["macro_f1"]
            save_checkpoint(
                model,
                tokenizer,
                args.output,
                {
                    "dataset": str(args.dataset),
                    "sealed": str(args.sealed),
                    "external_train": (
                        str(args.external_train) if args.external_train else None
                    ),
                    "external_test": (
                        str(args.external_test) if args.external_test else None
                    ),
                    "external_weight": args.external_weight,
                    "base_model": args.base_model,
                    "output": str(args.output),
                    "epochs": args.epochs,
                    "batch_size": args.batch_size,
                    "learning_rate": args.learning_rate,
                    "max_length": args.max_length,
                    "freeze_layers": args.freeze_layers,
                    "seed": args.seed,
                    "labels": LABELS,
                    "best_dev_macro_f1": best_macro_f1,
                },
            )

    checkpoint = torch.load(args.output / "model.pt", map_location=device)
    model.load_state_dict(checkpoint)
    dev_metrics = evaluate(model, dev_loader, device)
    sealed_metrics = evaluate(model, sealed_loader, device)
    external_test_metrics = (
        evaluate(model, external_test_loader, device)
        if external_test_loader
        else None
    )
    report = {
        "base_model": args.base_model,
        "device": str(device),
        "brighter_train_samples": len(train_rows),
        "external_train_samples": len(external_train_rows),
        "train_samples": len(combined_train_rows),
        "dev_samples": len(dev_rows),
        "sealed_test_samples": len(sealed_rows),
        "train_label_counts": dict(class_counts),
        "history": history,
        "best_dev_macro_f1": best_macro_f1,
        "dev": {key: value for key, value in dev_metrics.items()
                if key not in {"predictions", "expected", "confidences"}},
        "sealed_test": {key: value for key, value in sealed_metrics.items()
                        if key not in {"predictions", "expected", "confidences"}},
        "external_test": (
            {
                key: value
                for key, value in external_test_metrics.items()
                if key not in {"predictions", "expected", "confidences"}
            }
            if external_test_metrics
            else None
        ),
        "sealed_label_counts": dict(Counter(row["label"] for row in sealed_rows)),
    }
    (args.output / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (args.output / "sealed-predictions.jsonl").open("w", encoding="utf-8") as stream:
        for row, expected, predicted, confidence in zip(
            sealed_rows,
            sealed_metrics["expected"],
            sealed_metrics["predictions"],
            sealed_metrics["confidences"],
        ):
            stream.write(
                json.dumps(
                    {
                        "id": row["id"],
                        "text": row["text"],
                        "label": expected,
                        "predicted": predicted,
                        "confidence": confidence,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
