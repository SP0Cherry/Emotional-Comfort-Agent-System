#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

export HF_HOME="$PROJECT_DIR/.model-cache/huggingface"
export MODELSCOPE_CACHE="$PROJECT_DIR/.model-cache/modelscope"
export PRELOAD_TEXT="${PRELOAD_TEXT:-0}"
export PRELOAD_FINETUNED="${PRELOAD_FINETUNED:-1}"
export PRELOAD_SPEECH="${PRELOAD_SPEECH:-1}"
export PRELOAD_SPEECH_EMOTION="${PRELOAD_SPEECH_EMOTION:-1}"
export MODEL_SERVICE_PORT="${MODEL_SERVICE_PORT:-5055}"

exec "$PROJECT_DIR/.venv-speech/bin/python" scripts/model_service.py
