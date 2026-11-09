#!/usr/bin/env python3
"""Train a frozen-feature neutral gate and emotional fine-class stacker."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from train_multitask_text import (
    EmotionDataset,
    LABELS,
    LABEL_TO_ID,
    MultiTaskEmotionModel,
    expected_calibration_error,
    load_jsonl,
    macro_f1,
    per_class_metrics,
)
from transformers import AutoTokenizer


FINE_LABELS = ["joy", "sadness", "anxiety", "anger_irritation"]
FINE_TO_ID = {label: index for index, label in enumerate(FINE_LABELS)}


class HierarchicalStacker(nn.Module):
    def __init__(self, hidden_size=768):
        super().__init__()
        self.network = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, 256),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Dropout(0.1),
        )
        self.gate = nn.Linear(128, 1)
        self.fine = nn.Linear(128, len(FINE_LABELS))

    def forward(self, features):
        hidden = self.network(features)
        return {
            "gate": self.gate(hidden).squeeze(-1),
            "fine": self.fine(hidden),
        }


def extract_features(model, rows, tokenizer, batch_size, device):
    dataset = EmotionDataset(rows, tokenizer, 192)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    features = []
    labels = []
    sample_weights = []
    model.eval()
    with torch.inference_mode():
        for batch in loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            output = model.backbone(
                input_ids=input_ids,
                attention_mask=attention_mask,
            )
            mask = attention_mask.unsqueeze(-1).float()
            pooled = (output.last_hidden_state * mask).sum(1) / mask.sum(
                1
            ).clamp(min=1)
            features.append(pooled.cpu())
            labels.extend(batch["labels"].tolist())
            sample_weights.extend(batch["sample_weight"].tolist())
    return (
        torch.cat(features),
        torch.tensor(labels, dtype=torch.long),
        torch.tensor(sample_weights, dtype=torch.float32),
    )


def output_from_stacker(outputs, threshold):
    gate = torch.sigmoid(outputs["gate"])
    fine = torch.softmax(outputs["fine"], dim=-1)
    predictions = []
    confidences = []
    for emotional_probability, fine_probabilities in zip(gate, fine):
        if emotional_probability < threshold:
            predictions.append("neutral")
            confidences.append(float(1 - emotional_probability))
        else:
            index = int(fine_probabilities.argmax())
            predictions.append(FINE_LABELS[index])
            confidences.append(float(emotional_probability * fine_probabilities[index]))
    return predictions, confidences


def evaluate_outputs(labels, predictions, confidences):
    expected = [LABELS[index] for index in labels.tolist()]
    correct = [int(y == p) for y, p in zip(expected, predictions)]
    negative_expected = [label != "neutral" for label in expected]
    negative_predicted = [label != "neutral" for label in predictions]
    tp = sum(y and p for y, p in zip(negative_expected, negative_predicted))
    fp = sum(not y and p for y, p in zip(negative_expected, negative_predicted))
    fn = sum(y and not p for y, p in zip(negative_expected, negative_predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "accuracy": sum(correct) / len(correct),
        "macro_f1": macro_f1(expected, predictions),
        "per_class": per_class_metrics(expected, predictions),
        "ece": expected_calibration_error(confidences, correct),
        "negative_f1": (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        ),
        "negative_recall": recall,
        "negative_precision": precision,
        "samples": len(correct),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/brighter-johnson-multitask"),
    )
    parser.add_argument("--external-train", type=Path)
    parser.add_argument("--external-test", type=Path)
    parser.add_argument(
        "--sealed",
        type=Path,
        default=Path("evaluation/brighter-sealed-test.jsonl"),
    )
    parser.add_argument("--external-weight", type=float, default=0.5)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/hierarchical-stacker"),
    )
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
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
    external_train_rows = (
        [row for row in load_jsonl(args.external_train) if row["split"] == "train"]
        if args.external_train
        else []
    )
    external_test_rows = (
        [row for row in load_jsonl(args.external_test) if row["split"] == "test"]
        if args.external_test
        else []
    )
    combined_train_rows = train_rows + external_train_rows
    training_weights = [1.0] * len(train_rows) + [
        args.external_weight
    ] * len(external_train_rows)

    training_config = json.loads(
        (args.model / "training_config.json").read_text(encoding="utf-8")
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    encoder = MultiTaskEmotionModel(training_config["base_model"])
    encoder.load_state_dict(
        torch.load(args.model / "model.pt", map_location="cpu")
    )
    encoder.to(device)

    train_features = extract_features(
        encoder,
        combined_train_rows,
        tokenizer,
        args.batch_size,
        device,
    )
    train_features = (
        train_features[0],
        train_features[1],
        torch.tensor(training_weights, dtype=torch.float32),
    )
    dev_features = extract_features(
        encoder, dev_rows, tokenizer, args.batch_size, device
    )
    sealed_features = extract_features(
        encoder, sealed_rows, tokenizer, args.batch_size, device
    )
    external_test_features = (
        extract_features(
            encoder, external_test_rows, tokenizer, args.batch_size, device
        )
        if external_test_rows
        else None
    )

    train_loader = DataLoader(
        TensorDataset(
            train_features[0],
            train_features[1],
            train_features[2],
        ),
        batch_size=args.batch_size,
        shuffle=True,
    )
    stacker = HierarchicalStacker(train_features[0].shape[1]).to(device)
    optimizer = torch.optim.AdamW(
        stacker.parameters(),
        lr=args.learning_rate,
        weight_decay=0.01,
    )
    train_counts = Counter(
        LABELS[index] for index in train_features[1].tolist()
    )
    fine_counts = Counter(
        LABELS[index]
        for index in train_features[1].tolist()
        if LABELS[index] != "neutral"
    )
    fine_weights = torch.tensor(
        [
            sum(fine_counts.values())
            / (len(FINE_LABELS) * max(1, fine_counts[label]))
            for label in FINE_LABELS
        ],
        dtype=torch.float32,
        device=device,
    )
    neutral_count = train_counts["neutral"]
    emotional_count = sum(train_counts.values()) - neutral_count
    positive_weight = torch.tensor(
        neutral_count / max(1, emotional_count),
        dtype=torch.float32,
        device=device,
    )

    best = None
    history = []
    for epoch in range(args.epochs):
        stacker.train()
        epoch_loss = 0.0
        for features, labels, sample_weights in train_loader:
            features = features.to(device)
            labels = labels.to(device)
            sample_weights = sample_weights.to(device)
            output = stacker(features)
            gate_target = (labels != LABEL_TO_ID["neutral"]).float()
            gate_loss = nn.functional.binary_cross_entropy_with_logits(
                output["gate"],
                gate_target,
                reduction="none",
                pos_weight=positive_weight,
            )
            fine_targets = []
            fine_mask = []
            for index in labels.tolist():
                label = LABELS[index]
                if label == "neutral":
                    fine_targets.append(0)
                    fine_mask.append(0.0)
                else:
                    fine_targets.append(FINE_TO_ID[label])
                    fine_mask.append(1.0)
            fine_targets = torch.tensor(
                fine_targets,
                dtype=torch.long,
                device=device,
            )
            fine_mask = torch.tensor(
                fine_mask,
                dtype=torch.float32,
                device=device,
            )
            fine_loss = nn.functional.cross_entropy(
                output["fine"],
                fine_targets,
                weight=fine_weights,
                reduction="none",
            )
            loss = (
                (gate_loss * sample_weights).mean()
                + (fine_loss * fine_mask * sample_weights).sum()
                / (fine_mask * sample_weights).sum().clamp(min=1)
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach())

        stacker.eval()
        with torch.inference_mode():
            dev_output = stacker(dev_features[0].to(device))
        best_threshold = 0.5
        best_dev = None
        for threshold in np.arange(0.2, 0.81, 0.01):
            predictions, confidences = output_from_stacker(
                dev_output,
                float(threshold),
            )
            result = evaluate_outputs(
                dev_features[1],
                predictions,
                confidences,
            )
            if (
                best_dev is None
                or result["macro_f1"] > best_dev["macro_f1"]
                or (
                    result["macro_f1"] == best_dev["macro_f1"]
                    and result["accuracy"] > best_dev["accuracy"]
                )
            ):
                best_threshold = float(threshold)
                best_dev = result
        record = {
            "epoch": epoch + 1,
            "loss": epoch_loss / len(train_loader),
            "threshold": best_threshold,
            "dev": best_dev,
        }
        history.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if best is None or best_dev["macro_f1"] > best["dev"]["macro_f1"]:
            best = record
            args.output.mkdir(parents=True, exist_ok=True)
            torch.save(stacker.state_dict(), args.output / "model.pt")
            (args.output / "config.json").write_text(
                json.dumps(
                    {
                        "model_dir": str(args.model),
                        "labels": LABELS,
                        "fine_labels": FINE_LABELS,
                        "threshold": best_threshold,
                        "history": history,
                        "best_dev": best_dev,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    stacker.load_state_dict(
        torch.load(args.output / "model.pt", map_location=device)
    )
    stacker.eval()
    with torch.inference_mode():
        sealed_output = stacker(sealed_features[0].to(device))
        external_output = (
            stacker(external_test_features[0].to(device))
            if external_test_features
            else None
        )
    sealed_predictions, sealed_confidences = output_from_stacker(
        sealed_output,
        best["threshold"],
    )
    sealed_metrics = evaluate_outputs(
        sealed_features[1],
        sealed_predictions,
        sealed_confidences,
    )
    external_metrics = None
    if external_output is not None:
        external_predictions, external_confidences = output_from_stacker(
            external_output,
            best["threshold"],
        )
        external_metrics = evaluate_outputs(
            external_test_features[1],
            external_predictions,
            external_confidences,
        )
    report = {
        "model_dir": str(args.model),
        "threshold": best["threshold"],
        "history": history,
        "best_dev": best["dev"],
        "sealed_test": sealed_metrics,
        "external_test": external_metrics,
    }
    (args.output / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
