#!/usr/bin/env python3
"""Build a deterministic external Mandarin emotion benchmark."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from huggingface_hub import hf_hub_download
from opencc import OpenCC


SOURCE_ID = "Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset"
SOURCE_URL = f"https://huggingface.co/datasets/{SOURCE_ID}"
SOURCE_LICENSE = "MIT"
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_DIR / "evaluation" / "external-chinese-dialogue.jsonl"
MANIFEST_PATH = PROJECT_DIR / "evaluation" / "external-chinese-dialogue-manifest.json"
LABEL_MAP = {
    "平淡語氣": "neutral",
    "開心語調": "joy",
    "關切語調": "anxiety",
    "憤怒語調": "anger_irritation",
    "悲傷語調": "sadness",
    "厭惡語調": "anger_irritation",
}
EXCLUDED_LABELS = ["驚奇語調", "疑問語調"]


def stable_split(text: str) -> str:
    value = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
    bucket = value % 10
    if bucket == 0:
        return "dev"
    if bucket in {1, 2}:
        return "test"
    return "train"


def normalize_text(text: str, converter: OpenCC) -> str:
    simplified = converter.convert(text.strip())
    return re.sub(r"\s+", " ", simplified)


def main() -> None:
    source_path = Path(
        hf_hub_download(
            SOURCE_ID,
            "data.csv",
            repo_type="dataset",
        )
    )
    raw = source_path.read_bytes()
    source_sha256 = hashlib.sha256(raw).hexdigest()
    converter = OpenCC("t2s")

    rows_by_text = {}
    skipped_labels = Counter()
    skipped_empty = 0
    duplicates = 0
    with source_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            source_label = row["emotion"].strip()
            if source_label in EXCLUDED_LABELS:
                skipped_labels[source_label] += 1
                continue
            label = LABEL_MAP.get(source_label)
            if label is None:
                skipped_labels[source_label] += 1
                continue
            text = normalize_text(row["text"], converter)
            if not text:
                skipped_empty += 1
                continue
            key = re.sub(r"[\W_]+", "", text, flags=re.UNICODE).lower()
            if key in rows_by_text:
                duplicates += 1
                continue
            rows_by_text[key] = {
                "id": f"external-{len(rows_by_text) + 1:05d}",
                "text": text,
                "label": label,
                "source_label": source_label,
                "split": stable_split(key),
                "source": SOURCE_ID,
                "source_url": SOURCE_URL,
                "license": SOURCE_LICENSE,
            }

    rows = list(rows_by_text.values())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    counts = Counter(row["split"] for row in rows)
    label_counts = Counter(row["label"] for row in rows)
    split_label_counts = {
        split: Counter(row["label"] for row in rows if row["split"] == split)
        for split in ("train", "dev", "test")
    }
    manifest = {
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "source_license": SOURCE_LICENSE,
        "source_sha256": source_sha256,
        "output_sha256": hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest(),
        "original_rows": 4159,
        "mapped_rows": len(rows),
        "split_counts": dict(counts),
        "label_counts": dict(label_counts),
        "split_label_counts": {
            key: dict(value) for key, value in split_label_counts.items()
        },
        "excluded_labels": skipped_labels,
        "empty_rows": skipped_empty,
        "duplicates_removed": duplicates,
        "split_method": "SHA-256 text bucket: 10% dev, 20% test, 70% train",
        "speaker_isolated": False,
        "gold_label_warning": (
            "Original dataset has no speaker IDs and visible label noise. "
            "Use as external stress test, not a gold speaker-independent benchmark."
        ),
        "training_overlap_warning": (
            "Chinese-Emotion-Small was trained on this source. Do not report it "
            "as an independent generalization result."
        ),
        "include_classifier": False,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
