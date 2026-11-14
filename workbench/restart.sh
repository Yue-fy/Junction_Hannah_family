#!/usr/bin/env bash
# (Re)start the expert workbench on 127.0.0.1:${PORT:-8200}. Run from the repo root (any worktree).
# Test instance: PORT=8299 WORKBENCH_HUMAN_DIR=/some/scratch/human workbench/restart.sh
set -euo pipefail
PORT=${PORT:-8200}
SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
VENV=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}
LOG=${LOG:-$SHARED/logs/workbench$([ "$PORT" = 8200 ] || echo "-$PORT").log}
pid=$(ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true)
if [ -n "${pid:-}" ]; then kill "$pid"; sleep 1; fi
echo "[$(date +%H:%M:%S)] start workbench on :$PORT from $(pwd) ($(git rev-parse --short HEAD 2>/dev/null))" >> "$LOG"
setsid nohup "$VENV/bin/python" -m uvicorn workbench.app:app --host 127.0.0.1 --port "$PORT" >> "$LOG" 2>&1 < /dev/null &
for i in $(seq 1 30); do
  if curl -sf "127.0.0.1:$PORT/api/health" >/dev/null; then curl -s "127.0.0.1:$PORT/api/health"; echo; exit 0; fi
  sleep 0.5
done
echo "workbench did not come up; see $LOG" >&2; exit 1
