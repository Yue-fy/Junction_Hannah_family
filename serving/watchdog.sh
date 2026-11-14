#!/usr/bin/env bash
# Restart a model server that DIED (owner: R2). For the day after the night shift, when nobody watches :8001/:8002.
# usage: serving/watchdog.sh            (normally started detached: see the bottom of this comment)
# Rules, conservative on purpose:
#   - A port is restarted only when its pid file still exists, that pid is dead, AND /v1/models does not answer
#     on 2 checks in a row. serving/stop.sh removes the pid file, so a deliberate stop is never undone.
#   - A live but slow/unresponsive server is only logged, never killed.
#   - At most MAX_RESTARTS (3) restarts per port; then it gives up on that port and logs it.
#   - :8001 (the shared VLM + LoRAs, D2/D21) is restarted when ≥ 45 GB of GPU memory is free.
#     :8002 (Qwen3.6-35B, D21, optional: answers fall back to :8001) only when nobody holds the GPU lock and ≥ 48 GB is free (it needs 0.48 × 97.9).
#   - Pause/stop: touch $JUNCTION_SHARED/locks/watchdog.off (checked every loop). Stops by itself at UNTIL (19:00).
# Env: WATCH="8001 8002", INTERVAL=60, UNTIL=19:00, MAX_RESTARTS=3, DRY=1 (log the action, start nothing).
# Start detached:  setsid nohup serving/watchdog.sh >> $JUNCTION_SHARED/logs/watchdog.log 2>&1 < /dev/null &
set -uo pipefail
cd "$(dirname "$0")/.."
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
export JUNCTION_SHARED=$SHARED
WATCH=${WATCH:-8001 8002}
INTERVAL=${INTERVAL:-60}
UNTIL=${UNTIL:-19:00}
MAX_RESTARTS=${MAX_RESTARTS:-3}
DRY=${DRY:-0}
OFF=$SHARED/locks/watchdog.off
LOCK=$SHARED/locks/gpu.lock
declare -A fails restarts
log() { echo "[$(date +%H:%M:%S)] watchdog: $*"; }
pidfile() { if [[ $1 == 8001 ]]; then echo "$SHARED/logs/model-server.pid"; else echo "$SHARED/logs/model-server-$1.pid"; fi; }
healthy() { curl -s -m 10 "http://127.0.0.1:$1/v1/models" >/dev/null 2>&1; }
free_gb() { nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | awk '{print int($1/1024)}'; }
start_port() {  # mirrors how each server was started tonight (board/R2.md, DECISIONS D21)
  case $1 in
    8001) serving/start.sh ;;
    8002) PORT=8002 GPU_UTIL=0.48 SERVED_NAME=qwen3.6-35b-a3b serving/start.sh qwen36-35b-a3b ;;
    *) log "no start recipe for :$1"; return 1 ;;
  esac
}
log "started (pid $$): watching $WATCH every ${INTERVAL}s until $UNTIL, max $MAX_RESTARTS restarts/port, DRY=$DRY"
while :; do
  [[ -e $OFF ]] && { log "$OFF exists: exiting"; exit 0; }
  [[ $(date +%H:%M) > $UNTIL || $(date +%H:%M) == "$UNTIL" ]] && { log "reached $UNTIL: exiting"; exit 0; }
  for port in $WATCH; do
    if healthy "$port"; then fails[$port]=0; continue; fi
    pf=$(pidfile "$port")
    if [[ ! -f $pf ]]; then fails[$port]=0; continue; fi   # stopped on purpose (stop.sh) or never started: leave it
    pid=$(cat "$pf")
    if kill -0 "$pid" 2>/dev/null; then log ":$port not answering but pid $pid is alive: not touching it"; continue; fi
    fails[$port]=$(( ${fails[$port]:-0} + 1 ))
    log ":$port down, pid $pid dead (check ${fails[$port]})"
    (( ${fails[$port]} < 2 )) && continue
    if (( ${restarts[$port]:-0} >= MAX_RESTARTS )); then log ":$port gave up after $MAX_RESTARTS restarts"; continue; fi
    need=45; [[ $port != 8001 ]] && need=48
    for c in $(pgrep -g "$pid" 2>/dev/null); do   # leftover engine-core children of the dead server (its process group)
      ps -o args= -p "$c" 2>/dev/null | grep -q "coder390-vllm" && kill -TERM "$c" 2>/dev/null
    done
    sleep 5
    free=${FREE_GB:-$(free_gb)}   # FREE_GB: test override only
    if (( ${free:-0} < need )); then log ":$port needs ${need} GB, GPU has ${free:-?} GB free: waiting"; continue; fi
    if [[ $port != 8001 ]] && ! flock -n "$LOCK" true; then log ":$port: GPU lock is held (someone's job): waiting"; continue; fi
    restarts[$port]=$(( ${restarts[$port]:-0} + 1 ))
    log ":$port restart ${restarts[$port]}/$MAX_RESTARTS"
    if [[ $DRY == 1 ]]; then log "DRY: would run start_port $port"; rm -f "$pf"; continue; fi
    if start_port "$port"; then log ":$port back up"; fails[$port]=0; else log ":$port restart failed (see its model-server log)"; fi
  done
  sleep "$INTERVAL"
done
