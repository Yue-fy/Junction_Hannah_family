#!/usr/bin/env bash
# The W1 regression recipe in one command: ifc on train/dev/hard/hard2 + pipeline on dev/hard (all --source
# ifc_models, ~2 min in parallel), each diffed question by question against a baseline run. Use it after ANY change
# to stoa/solvers/ifc/ or to a pipeline step that IFC questions pass through.
#
# Usage (from the repo root):  experiments/w1/regress.sh [EXTRA_SPLIT.jsonl]
#   EXTRA_SPLIT: an optional ad-hoc split (e.g. Stoa's noon examples, Q's red-team IFC rows) run on the pipeline too;
#   it is not diffed (no baseline): read its accuracy line and compare by hand.
# Baselines: the night freeze head's runs (W1 cycle 9, night-W1 daf7b4f on night b656826); override with BASE_<NAME>=<run id>.
# Output: one line per run "N changed of M" (+ the changed rows: old conf, new conf, old/new correct, qid, values).
# "0 changed" everywhere = safe. Any change: read the rows; a change that is not the one you meant is a regression.
set -u
PY=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
E=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}/artifacts/eval
LOG=logs/regress-$(date +%H%M%S)
mkdir -p "$LOG"
declare -A BASE=(
  [ifc-train]=${BASE_IFC_TRAIN:-20261114-110550-ifc-train-63b2}
  [ifc-dev]=${BASE_IFC_DEV:-20261114-110550-ifc-dev-98bf}
  [ifc-hard]=${BASE_IFC_HARD:-20261114-110549-ifc-hard-61f8}
  [ifc-hard2]=${BASE_IFC_HARD2:-20261114-110549-ifc-hard2-d4a8}
  [pipeline-dev]=${BASE_PIPELINE_DEV:-20261114-110550-pipeline-dev-aaa6}
  [pipeline-hard]=${BASE_PIPELINE_HARD:-20261114-110549-pipeline-hard-3f58}
)
for s in train dev hard hard2; do
  "$PY" -m stoa.eval --solver ifc --split "$s" --source ifc_models > "$LOG/ifc-$s.log" 2>&1 &
done
for s in dev hard; do
  "$PY" -m stoa.eval --solver pipeline --split "$s" --source ifc_models > "$LOG/pipeline-$s.log" 2>&1 &
done
if [ $# -ge 1 ]; then
  "$PY" -m stoa.eval --solver pipeline --split "$1" > "$LOG/pipeline-extra.log" 2>&1 &
fi
wait
for k in ifc-train ifc-dev ifc-hard ifc-hard2 pipeline-dev pipeline-hard; do
  new=$(grep -o "$E/[^ ]*\.jsonl" "$LOG/$k.log" | tail -n 1)
  old="$E/${BASE[$k]}.jsonl"
  echo "== $k: $(basename "${new:-<run failed: see $LOG/$k.log>}") vs ${BASE[$k]}"
  if [ -n "$new" ] && [ -f "$old" ]; then
    "$PY" experiments/w1/diff_runs.py "$old" "$new" | tail -n 30
  fi
done
if [ $# -ge 1 ]; then
  echo "== extra split $1 (no baseline):"
  grep -E "accuracy|acc |conf>=0.8|predictions:" "$LOG/pipeline-extra.log" | head -n 6
fi
echo "logs: $LOG"
