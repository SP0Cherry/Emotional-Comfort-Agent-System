#!/usr/bin/env python3
"""Load SenseVoiceSmall and transcribe one bundled Mandarin sample."""

from __future__ import annotations

import json
import time

from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from huggingface_hub import hf_hub_download


MODEL_ID = "FunAudioLLM/SenseVoiceSmall"


def main() -> None:
    sample_path = hf_hub_download(MODEL_ID, "example/zh.mp3")
    load_started_at = time.perf_counter()
    model = AutoModel(
        model=MODEL_ID,
        hub="hf",
        device="cpu",
        disable_update=True,
    )
    load_seconds = time.perf_counter() - load_started_at

    inference_started_at = time.perf_counter()
    result = model.generate(
        input=sample_path,
        cache={},
        language="zh",
        use_itn=True,
        batch_size_s=60,
    )
    inference_seconds = time.perf_counter() - inference_started_at
    text = rich_transcription_postprocess(result[0]["text"])

    print(
        json.dumps(
            {
                "model_id": MODEL_ID,
                "sample_path": sample_path,
                "load_seconds": round(load_seconds, 2),
                "inference_seconds": round(inference_seconds, 2),
                "raw_text": result[0]["text"],
                "processed_text": text,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
