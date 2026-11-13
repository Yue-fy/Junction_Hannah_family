#!/usr/bin/env bash
# Start the shared OpenAI-compatible model server (vLLM) on port 8001.
# Usage: serving/start.sh [preset]      presets: qwen3vl8b (default), qwen35-9b, qwen36-35b-a3b
# Env overrides: MODEL, SERVED_NAME, PORT, GPU_UTIL, MAX_LEN, EXTRA_ARGS
# Survives the calling shell (setsid+nohup). Log: $JUNCTION_SHARED/logs/model-server.log
set -euo pipefail
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
VENV=${VLLM_VENV:-/data/User/fangy4/envs/coder390-vllm}   # read-only use; we never install into it
MODELS=${MODEL_DIR:-/data/User/fangy4/models}
PRESET=${1:-qwen3vl8b}
export PATH="$VENV/bin:$PATH"   # flashinfer JIT needs ninja from the env
case "$PRESET" in
  qwen3vl8b)
    : "${MODEL:=$MODELS/hf/local/Qwen3-VL-8B-Instruct-from-QwenImage2.1}"
    : "${SERVED_NAME:=qwen3-vl-8b}" ;;
  qwen35-9b)
    : "${MODEL:=$MODELS/hf/Qwen/Qwen3.5-9B}"
    : "${SERVED_NAME:=qwen3.5-9b}" ;;
  qwen36-35b-a3b)
    : "${MODEL:=$MODELS/hf/Qwen/Qwen3.6-35B-A3B-FP8}"
    : "${SERVED_NAME:=qwen3.6-35b-a3b}" ;;
  *) : "${MODEL:?set MODEL for a custom preset}"; : "${SERVED_NAME:=$PRESET}" ;;
esac
PORT=${PORT:-8001}
GPU_UTIL=${GPU_UTIL:-0.45}
MAX_LEN=${MAX_LEN:-32768}
LOG=$SHARED/logs/model-server.log
PIDF=$SHARED/logs/model-server.pid

if curl -s -m 2 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
  echo "Something already serves on :$PORT. Run serving/stop.sh first."; exit 1
fi
echo "[$(date +%H:%M)] starting $SERVED_NAME from $MODEL (util=$GPU_UTIL, max_len=$MAX_LEN)" | tee -a "$LOG"
# --served-model-name: first name is the specific model, "default" is a stable alias for clients.
setsid nohup "$VENV/bin/vllm" serve "$MODEL" \
  --host 127.0.0.1 --port "$PORT" \
  --served-model-name "$SERVED_NAME" default \
  --gpu-memory-utilization "$GPU_UTIL" \
  --max-model-len "$MAX_LEN" \
  --max-num-seqs 32 \
  --limit-mm-per-prompt '{"image": 8, "video": 0}' \
  --trust-remote-code \
  ${EXTRA_ARGS:-} >> "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDF"
echo "pid $(cat "$PIDF"); waiting for /v1/models ..."
for i in $(seq 1 180); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then echo "ready after $((i*5))s"; exit 0; fi
  if ! kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "server died; see $LOG"; tail -30 "$LOG"; exit 1; fi
  sleep 5
done
echo "not ready after 15 min; see $LOG"; exit 1
