#!/usr/bin/env bash
# One command before a demo (run from anywhere):  web/demo.sh
#   1. API: uses STOA_API_URL (default http://127.0.0.1:8100) if it answers /health, else starts one from this
#      checkout on that port (uvicorn stoa.api:app).
#   2. Local model server (LLM_BASE_URL, default http://127.0.0.1:8001/v1): only checked. IFC, Swiss PDF/DXF and
#      schedule answers need no model; CubiCasa counts, scans and the reasoning agent do.
#   3. Web: Vite dev server on :5173 (started if not running), pointed at that API.
#   4. Warm-up: asks every demo-tour question once (fixtures/tour.json + extras, incl. one hosted Nemotron call per
#      second-opinion step), so the presenter's answers come from the API cache in milliseconds.
#      fixtures/recorded.json is not changed. Skip with DEMO_WARM=0.
# Logs: $DEMO_LOG_DIR (default ${TMPDIR:-/tmp}/stoa-demo).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
API=${STOA_API_URL:-http://127.0.0.1:8100}
LLM=${LLM_BASE_URL:-http://127.0.0.1:8001/v1}
PY=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
LOGS=${DEMO_LOG_DIR:-${TMPDIR:-/tmp}/stoa-demo}
mkdir -p "$LOGS"

up() { curl -fsS -m 5 "$1" >/dev/null 2>&1; }
wait_for() { # url, seconds
  for _ in $(seq 1 "$2"); do up "$1" && return 0; sleep 1; done
  return 1
}

if up "$API/health"; then
  echo "API      $API (already running)"
else
  port=${API##*:}; port=${port%%/*}
  echo "API      starting on :$port from $ROOT (log $LOGS/api.log)"
  (cd "$ROOT" && setsid nohup "$PY" -m uvicorn stoa.api:app --port "$port" >"$LOGS/api.log" 2>&1 &)
  wait_for "$API/health" 60 || { echo "API did not come up; see $LOGS/api.log" >&2; exit 1; }
fi
curl -fsS -m 5 "$API/health" | "$PY" -c 'import json,sys; h=json.load(sys.stdin); print("         solvers:", ", ".join(h.get("solvers", [])), "| import errors:", h.get("import_errors") or "none")'

if up "$LLM/models"; then
  echo "LLM      $LLM: $(curl -fsS -m 5 "$LLM/models" | "$PY" -c 'import json,sys; print(", ".join(m["id"] for m in json.load(sys.stdin)["data"]))')"
else
  echo "LLM      $LLM is DOWN: IFC / Swiss / schedule steps still work; CubiCasa, scans and the agent will fail or fall back" >&2
fi

if up "http://127.0.0.1:5173/"; then
  echo "Web      http://localhost:5173 (already running; its API is whatever STOA_API_URL it was started with)"
else
  echo "Web      starting Vite on :5173 (log $LOGS/web.log)"
  (cd "$ROOT/web" && STOA_API_URL="$API" setsid nohup npm run dev >"$LOGS/web.log" 2>&1 &)
  wait_for "http://127.0.0.1:5173/" 60 || { echo "Vite did not come up; see $LOGS/web.log" >&2; exit 1; }
fi

if [ "${DEMO_WARM:-1}" != "0" ]; then
  echo "Warm-up  asking the tour questions once (first run of a scan/agent question can take minutes)…"
  (cd "$ROOT" && "$PY" -u web/fixtures/record.py --api "$API" --no-write) | sed 's/^/         /'
fi
echo "Ready    http://localhost:5173  ·  'Demo tour ▸' or → / ← to step  ·  'How well it works' for the bench"
