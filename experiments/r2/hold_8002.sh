#!/usr/bin/env bash
# Hold the GPU lock and keep a private model server on :8002 up for a time-boxed bake-off. Owner: R2.
# Usage: experiments/r2/hold_8002.sh <preset> <served_name> <minutes>
#   Stops early when $JUNCTION_SHARED/locks/R2-8002.stop exists (touch it to release the GPU).
set -euo pipefail
PRESET=$1; NAME=$2; MIN=${3:-60}
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
STOPF=$SHARED/locks/R2-8002.stop; rm -f "$STOPF"
exec 9>"$SHARED/locks/gpu.lock"
echo "[$(date +%H:%M)] waiting for the GPU lock ..."; flock 9
echo "[$(date +%H:%M)] got the GPU lock; serving $PRESET on :8002 for <= $MIN min"
cleanup() { "$REPO/serving/stop.sh" 8002 || true; echo "[$(date +%H:%M)] released"; }
trap cleanup EXIT
cd "$REPO"
PORT=8002 GPU_UTIL=${GPU_UTIL:-0.48} MAX_LEN=${MAX_LEN:-32768} SERVED_NAME="$NAME" serving/start.sh "$PRESET" 9>&-
end=$(( $(date +%s) + MIN*60 ))
while [[ $(date +%s) -lt $end && ! -f $STOPF ]]; do sleep 10; done
