#!/usr/bin/env python3
"""Load the Mandarin text emotion model and classify one sample."""

from __future__ import annotations

import json
import os
import time

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


MODEL_ID = os.environ.get("TEXT_MODEL_ID", "Johnson8187/Chinese-Emotion-Small")
SAMPLES = [
    "明天要答辩了，我一直睡不着，担心会搞砸。",
    "雨停了，事情也办成了，心里亮堂多了。",
    "今天没有特别高兴，也没那么难过。",
    "我快气死了。",
    "今天真是太开心了！",
    "我覺得自己一無是處，真的很難過。",
    "我完全沒想到你會這麼做，這讓我驚訝到無法言喻。",
    "怎麼會這樣？",
]


def choose_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main() -> None:
    started_at = time.perf_counter()
    device = choose_device()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
    model.to(device)
    model.eval()

    loaded_seconds = time.perf_counter() - started_at
    outputs = []
    for text in SAMPLES:
        inference_started = time.perf_counter()
        encoded = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
        )
        encoded = {name: value.to(device) for name, value in encoded.items()}
        with torch.inference_mode():
            logits = model(**encoded).logits[0]
            is_multilabel = (
                getattr(model.config, "problem_type", None)
                == "multi_label_classification"
            )
            probabilities = (
                torch.sigmoid(logits)
                if is_multilabel
                else torch.softmax(logits, dim=-1)
            )

        scores = {
            model.config.id2label[index]: float(probability)
            for index, probability in enumerate(probabilities)
        }
        outputs.append(
            {
                "text": text,
                "predicted": max(scores, key=scores.get),
                "scores": scores,
                "multi_label": is_multilabel,
                "latency_ms": round(
                    (time.perf_counter() - inference_started) * 1000,
                    2,
                ),
            }
        )

    print(
        json.dumps(
            {
                "model_id": MODEL_ID,
                "device": str(device),
                "loaded_seconds": round(loaded_seconds, 2),
                "labels": model.config.id2label,
                "outputs": outputs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
