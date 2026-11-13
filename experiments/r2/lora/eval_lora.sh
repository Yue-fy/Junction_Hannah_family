#!/usr/bin/env bash
# Evaluate a LoRA adapter on a PRIVATE vLLM instance (:8002) without touching the shared server (:8001).
# Holds the GPU lock for the whole run (start instance -> evals -> stop instance), so it can be queued while a
# training run still holds the lock: it starts only after the trainer has saved and exited.
# Usage: experiments/r2/lora/eval_lora.sh <adapter_name> <adapter_dir> [eval args...] [--next eval args...]...
#   e.g. experiments/r2/lora/eval_lora.sh cc-v2 $JUNCTION_SHARED/artifacts/R2/lora/cc-v2 \
#          --split dev --source cubicasa5k --next --split train_gate --source cubicasa5k
set -euo pipefail
NAME=$1; DIR=$2; shift 2
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
J=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
[[ $# -gt 0 ]] || set -- --split dev --source cubicasa5k

exec 9>"$SHARED/locks/gpu.lock"
echo "[$(date +%H:%M)] waiting for the GPU lock ..."; flock 9
echo "[$(date +%H:%M)] got the GPU lock"
[[ -f $DIR/adapter_config.json ]] || { echo "no adapter in $DIR"; exit 1; }
cleanup() { "$REPO/serving/stop.sh" 8002 || true; }
trap cleanup EXIT
cd "$REPO"
PORT=8002 GPU_UTIL=${GPU_UTIL:-0.30} SERVED_NAME=qwen3-vl-8b-lora-test LORA="$NAME=$DIR" serving/start.sh qwen3vl8b 9>&-   # the server must not inherit the lock fd

run() {
  echo "[$(date +%H:%M)] eval: $*"
  LLM_BASE_URL=http://127.0.0.1:8002/v1 "$J" -m stoa.eval --solver vlm_direct --workers 24 \
    --solver-arg model="$NAME" --note "R2 LoRA $NAME ($DIR) on private :8002" "$@" 2>&1 | grep -v "it/s" || true
}
ARGS=()
for x in "$@"; do
  if [[ $x == --next ]]; then run "${ARGS[@]}"; ARGS=(); else ARGS+=("$x"); fi
done
[[ ${#ARGS[@]} -gt 0 ]] && run "${ARGS[@]}"
echo "[$(date +%H:%M)] done"
