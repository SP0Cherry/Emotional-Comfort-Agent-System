#!/usr/bin/env python3
"""Build the official Mandarin BRIGHTER dev/test dominant-emotion benchmark."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download
from opencc import OpenCC


SOURCE_ID = "brighter-dataset/BRIGHTER-emotion-intensities"
SOURCE_URL = f"https://huggingface.co/datasets/{SOURCE_ID}"
SOURCE_LICENSE = "CC-BY-4.0"
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_DIR / "evaluation" / "brighter-chinese.jsonl"
MANIFEST_PATH = PROJECT_DIR / "evaluation" / "brighter-chinese-manifest.json"
EMOTION_FIELDS = {
    "anger": "anger_irritation",
    "disgust": "anger_irritation",
    "fear": "anxiety",
    "joy": "joy",
    "sadness": "sadness",
}


def main() -> None:
    converter = OpenCC("t2s")
    rows = []
    source_hashes = {}
    skipped = Counter()
    seen = set()

    # Keep the already-evaluated dev/test rows stable. Train rows are added last
    # and skip any text that appears in those splits to prevent leakage.
    for split in ("dev", "test", "train"):
        filename = f"chn/{split}-00000-of-00001.parquet"
        path = Path(
            hf_hub_download(
                SOURCE_ID,
                filename,
                repo_type="dataset",
            )
        )
        source_hashes[split] = hashlib.sha256(path.read_bytes()).hexdigest()
        for source_row in pq.read_table(path).to_pylist():
            text = re.sub(r"\s+", " ", converter.convert(source_row["text"].strip()))
            if not text:
                skipped["empty"] += 1
                continue
            key = re.sub(r"[\W_]+", "", text, flags=re.UNICODE).lower()
            if key in seen:
                skipped["duplicate"] += 1
                continue
            seen.add(key)

            intensities = {
                field: int(source_row.get(field, 0) or 0)
                for field in (*EMOTION_FIELDS, "surprise")
            }
            allowed_strengths = {
                label: intensities[field]
                for field, label in EMOTION_FIELDS.items()
                if intensities[field] > 0
            }
            if not allowed_strengths:
                if intensities["surprise"] > 0:
                    skipped["surprise_only"] += 1
                    continue
                label = "neutral"
            else:
                maximum = max(allowed_strengths.values())
                winners = [
                    label
                    for label, value in allowed_strengths.items()
                    if value == maximum
                ]
                if len(winners) > 1:
                    skipped["tie"] += 1
                    continue
                label = winners[0]

            rows.append(
                {
                    "id": source_row["id"],
                    "text": text,
                    "label": label,
                    "intensities": intensities,
                    "split": split,
                    "source": SOURCE_ID,
                    "source_url": SOURCE_URL,
                    "license": SOURCE_LICENSE,
                }
            )

    OUTPUT_PATH.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    split_counts = Counter(row["split"] for row in rows)
    split_labels = {
        split: Counter(row["label"] for row in rows if row["split"] == split)
        for split in ("dev", "test")
    }
    manifest = {
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "source_license": SOURCE_LICENSE,
        "source_sha256": source_hashes,
        "output_sha256": hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest(),
        "split_counts": dict(split_counts),
        "split_label_counts": {
            key: dict(value) for key, value in split_labels.items()
        },
        "skipped": dict(skipped),
        "label_rule": (
            "Official dev/test split; dominant emotion from highest non-zero "
            "intensity among anger, disgust, fear, joy, sadness. Ties and "
            "surprise-only rows are excluded. All-zero rows map to neutral."
        ),
        "speaker_isolated": False,
        "prediction_aliases": {"calm": "neutral"},
        "warning": (
            "Official benchmark split, but speaker IDs are unavailable. "
            "Calm is not annotated; calm predictions map to neutral for scoring."
        ),
        "evaluation_sample_limit": 1000,
        "evaluation_sampling": (
            "Deterministic stratified sample of up to 1000 test rows by label "
            "using SHA-256 ordering."
        ),
        "include_classifier": True,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
