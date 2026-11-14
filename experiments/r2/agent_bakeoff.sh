#!/usr/bin/env bash
# Does a stronger reasoning model help the general agent on unseen question kinds? Owner: R2.
# Serves a model preset on a PRIVATE :8002 (GPU lock held throughout) and runs W4's `agent` solver with
# backend=local2: only the agent's own planning / `look` calls go to :8002; every atomic solver the agent asks
# (dxf, ifc, vlm_lora, raster ...) stays on the shared :8001. Compare against the same split with backend=local.
# Usage: experiments/r2/agent_bakeoff.sh <preset> <served_name> [eval args...] [--next eval args...]...
#   e.g. GPU_UTIL=0.48 experiments/r2/agent_bakeoff.sh qwen36-35b-a3b qwen3.6-35b-a3b --split hard2
# Memory: Qwen3.6-35B-A3B-FP8 = 37.5 GB weights; next to :8001 (~48.7 GB) only ~49 GB are free -> GPU_UTIL ~0.48,
# and nothing else may hold GPU memory (that is what the lock guarantees for R2's jobs).
set -euo pipefail
PRESET=$1; NAME=$2; shift 2
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
J=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
REPO=$(cd "$(dirname "$0")/../.." && pwd)
[[ $# -gt 0 ]] || set -- --split hard2

exec 9>"$SHARED/locks/gpu.lock"
echo "[$(date +%H:%M)] waiting for the GPU lock ..."; flock 9
echo "[$(date +%H:%M)] got the GPU lock"
cleanup() { "$REPO/serving/stop.sh" 8002 || true; }
trap cleanup EXIT
cd "$REPO"
PORT=8002 GPU_UTIL=${GPU_UTIL:-0.48} MAX_LEN=${MAX_LEN:-32768} SERVED_NAME="$NAME" serving/start.sh "$PRESET" 9>&-

run() {
  echo "[$(date +%H:%M)] eval: $*"
  LLM2_BASE_URL=http://127.0.0.1:8002/v1 "$J" -m stoa.eval --solver agent --workers ${WORKERS:-4} \
    --solver-arg backend=local2 --note "R2 agent bake-off: planner $PRESET ($NAME) on :8002" "$@" 2>&1 \
    | grep -v "it/s" || true
}
ARGS=()
for x in "$@"; do
  if [[ $x == --next ]]; then run "${ARGS[@]}"; ARGS=(); else ARGS+=("$x"); fi
done
[[ ${#ARGS[@]} -gt 0 ]] && run "${ARGS[@]}"
echo "[$(date +%H:%M)] done"
