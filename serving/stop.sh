#!/usr/bin/env bash
# Stop the shared model server started by serving/start.sh.
set -uo pipefail
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
PIDF=$SHARED/logs/model-server.pid
if [[ -f $PIDF ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  PID=$(cat "$PIDF")
  # kill the whole session (vllm spawns an engine-core child process)
  kill -TERM -- "-$PID" 2>/dev/null || kill -TERM "$PID"
  for i in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
  kill -0 "$PID" 2>/dev/null && kill -KILL -- "-$PID" 2>/dev/null
  echo "[$(date +%H:%M)] stopped server pid $PID" | tee -a "$SHARED/logs/model-server.log"
  rm -f "$PIDF"
else
  echo "no running server pid file"
fi
