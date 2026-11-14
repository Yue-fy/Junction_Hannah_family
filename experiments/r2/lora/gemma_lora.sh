#!/usr/bin/env bash
# Gemma 4 E4B counting LoRA (Gemma prize + "small fine-tuned model"), TRAIN split only. Owner: R2.
# Steps, each under the GPU lock and leaving the shared server its memory:
#   1. smoke train (16 samples) to catch format/memory errors fast; 2. full train (time box MINUTES);
#   3. eval on a private :8002 Gemma instance with the adapter (eval_lora.sh, PRESET=gemma4-e4b).
# Usage: nohup setsid experiments/r2/lora/gemma_lora.sh > $JUNCTION_SHARED/logs/R2/gemma_lora.log 2>&1 &
set -euo pipefail
S=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
PY=/data/User/fangy4/envs/junction-train/bin/python
GEMMA=${GEMMA:-/data/User/fangy4/models/hf/google/gemma-4-E4B-it}
NAME=${NAME:-gemma-cc-v1}
OUT=${OUT:-$S/artifacts/R2/lora/$NAME}
DATA=${DATA:-$S/artifacts/R2/lora/train_v3_mix.jsonl}
MINUTES=${MINUTES:-50}
cd "$REPO"
until [ -f "$GEMMA/model.safetensors" ] && ! pgrep -f "hf download google/gemma-4-E4B-it" >/dev/null; do sleep 20; done

echo "[$(date +%H:%M)] smoke train"
flock "$S/locks/gpu.lock" "$PY" experiments/r2/lora/train_lora.py --arch gemma4 --model "$GEMMA" --data "$DATA" \
  --out "$S/artifacts/R2/lora/_gemma_smoke" --max-samples 16 --accum 4 --minutes 3
echo "[$(date +%H:%M)] full train -> $OUT"
flock "$S/locks/gpu.lock" "$PY" experiments/r2/lora/train_lora.py --arch gemma4 --model "$GEMMA" --data "$DATA" \
  --out "$OUT" --lr 1e-4 --minutes "$MINUTES"
echo "[$(date +%H:%M)] eval"
PRESET=gemma4-e4b experiments/r2/lora/eval_lora.sh "$NAME" "$OUT" \
  --split train_gate --source cubicasa5k --solver-arg conf=raw \
  --next --split dev --source cubicasa5k \
  --next --split "$S/artifacts/R2/swiss_png_counts_dev.jsonl" \
  --next --split "$S/artifacts/R2/cc5k_heldout_notLoRA.jsonl"
echo "[$(date +%H:%M)] all done"
