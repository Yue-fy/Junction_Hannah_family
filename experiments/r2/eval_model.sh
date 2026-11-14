#!/usr/bin/env bash
# Bake-off: evaluate a BASE model preset (serving/start.sh presets) on a PRIVATE vLLM instance (:8002) without
# touching the shared server (:8001). Holds the GPU lock for the whole run (start -> evals -> stop). Owner: R2.
# Usage: experiments/r2/eval_model.sh <preset> <served_name> [eval args...] [--next eval args...]...
#   e.g. experiments/r2/eval_model.sh gemma4-e4b gemma-4-e4b --split train_gate --source cubicasa5k
# Env: GPU_UTIL (default 0.30), SOLVER (default vlm_direct), any serving/start.sh env (EXTRA_ARGS, GEMMA_IMG_TOKENS).
set -euo pipefail
PRESET=$1; NAME=$2; shift 2
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
J=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
REPO=$(cd "$(dirname "$0")/../.." && pwd)
SOLVER=${SOLVER:-vlm_direct}
[[ $# -gt 0 ]] || set -- --split smoke

exec 9>"$SHARED/locks/gpu.lock"
echo "[$(date +%H:%M)] waiting for the GPU lock ..."; flock 9
echo "[$(date +%H:%M)] got the GPU lock"
cleanup() { "$REPO/serving/stop.sh" 8002 || true; }
trap cleanup EXIT
cd "$REPO"
PORT=8002 GPU_UTIL=${GPU_UTIL:-0.30} SERVED_NAME="$NAME" serving/start.sh "$PRESET" 9>&-   # server must not inherit the lock fd

run() {
  echo "[$(date +%H:%M)] eval: $*"
  LLM_BASE_URL=http://127.0.0.1:8002/v1 "$J" -m stoa.eval --solver "$SOLVER" --workers ${WORKERS:-4} \
    --solver-arg model="$NAME" --note "R2 bake-off $PRESET ($NAME) on private :8002" "$@" 2>&1 | grep -v "it/s" || true
}
ARGS=()
for x in "$@"; do
  if [[ $x == --next ]]; then run "${ARGS[@]}"; ARGS=(); else ARGS+=("$x"); fi
done
[[ ${#ARGS[@]} -gt 0 ]] && run "${ARGS[@]}"
echo "[$(date +%H:%M)] done"
