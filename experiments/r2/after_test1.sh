#!/usr/bin/env bash
# Runs R2's GPU work that S0's DECISION (03:23) deferred until sealed test 1 is done. Owner: R2.
#   1. wait until logs/S0/test1-driver.log contains 'done'
#   2. hot-load LoRA cc-v3 into the shared :8001 server (NO restart; cc-v2 keeps serving) -> vlm_lora uses it for
#      non-cubicasa raster plans
#   3. start the Gemma 4 E4B counting LoRA job (smoke -> train -> eval, under the GPU lock)
# Usage: nohup setsid experiments/r2/after_test1.sh > $JUNCTION_SHARED/logs/R2/after_test1.log 2>&1 &
set -uo pipefail
S=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
DRIVER=$S/logs/S0/test1-driver.log
until grep -qw 'done' "$DRIVER" 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M)] test 1 done: $(tail -1 "$DRIVER")"

if curl -s -m 5 http://127.0.0.1:8001/v1/models | grep -q '"cc-v3"'; then
  echo "cc-v3 already served"
else
  curl -s -m 120 -X POST http://127.0.0.1:8001/v1/load_lora_adapter -H 'Content-Type: application/json' \
    -d "{\"lora_name\":\"cc-v3\",\"lora_path\":\"$S/artifacts/R2/lora/cc-v3\"}"; echo
  curl -s -m 5 http://127.0.0.1:8001/v1/models | grep -o '"id":"[^"]*"' | tr '\n' ' '; echo
fi
echo "[$(date +%H:%M)] [R2] hot-loaded cc-v3 into :8001 (no restart)" >> "$S/logs/model-server.log"

cd "$REPO"
echo "[$(date +%H:%M)] starting the Gemma LoRA job"
exec experiments/r2/lora/gemma_lora.sh >> "$S/logs/R2/gemma_lora.log" 2>&1
