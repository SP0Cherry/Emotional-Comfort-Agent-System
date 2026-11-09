#!/usr/bin/env python3
"""Create the untouched BRIGHTER test complement after development evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = PROJECT_DIR / "evaluation" / "brighter-chinese.jsonl"
CHECKPOINT_PATH = (
    PROJECT_DIR / "outputs" / "brighter-chinese-eval-checkpoint.jsonl"
)
OUTPUT_PATH = PROJECT_DIR / "evaluation" / "brighter-sealed-test.jsonl"
MANIFEST_PATH = PROJECT_DIR / "evaluation" / "brighter-sealed-test-manifest.json"


def main() -> None:
    rows = [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    used_ids = {
        json.loads(line)["id"]
        for line in CHECKPOINT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    sealed = [
        row
        for row in rows
        if row["split"] == "test" and row["id"] not in used_ids
    ]
    if not sealed:
        raise RuntimeError("没有剩余未使用的官方 test 样本")
    OUTPUT_PATH.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in sealed) + "\n",
        encoding="utf-8",
    )
    counts = {}
    for row in sealed:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    manifest = {
        "source": "brighter-dataset/BRIGHTER-emotion-intensities",
        "split": "official test complement",
        "rows": len(sealed),
        "label_counts": counts,
        "excluded_development_ids": len(used_ids),
        "output_sha256": hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest(),
        "claim": (
            "These rows were not included in the 1000-row development/error-analysis "
            "sample. Use once for the final fine-tuned model evaluation."
        ),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
