#!/usr/bin/env python3
"""Run the dedicated speech emotion model on one local Mandarin WAV."""

from __future__ import annotations

import json
import time
from pathlib import Path

from funasr import AutoModel
from huggingface_hub import snapshot_download


MODEL_ID = "emotion2vec/emotion2vec_plus_base"
PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_PATH = PROJECT_DIR / "outputs" / "tmp" / "zh-smoke.wav"


def main() -> None:
    model_path = snapshot_download(
        MODEL_ID,
        local_files_only=False,
    )
    model_started_at = time.perf_counter()
    model = AutoModel(
        model=model_path,
        device="cpu",
        disable_update=True,
    )
    load_seconds = time.perf_counter() - model_started_at

    inference_started_at = time.perf_counter()
    result = model.generate(
        input=str(SAMPLE_PATH),
        granularity="utterance",
        extract_embedding=False,
    )
    inference_seconds = time.perf_counter() - inference_started_at
    print(
        json.dumps(
            {
                "model_id": MODEL_ID,
                "model_path": model_path,
                "load_seconds": round(load_seconds, 2),
                "inference_seconds": round(inference_seconds, 2),
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
