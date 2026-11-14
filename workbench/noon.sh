#!/usr/bin/env bash
# After the noon reveal: run our pipeline on Stoa's example questions and offer them to the expert on the workbench.
#   workbench/noon.sh SPLIT.jsonl [NAME=stoa] [LABEL="Stoa's example questions"]
#   workbench/noon.sh RUN_ID_OR_PREDICTIONS.jsonl ...   # reuse an existing pipeline run (e.g. from noon_models.sh)
#   workbench/noon.sh QUESTIONS.txt ...                 # one question per line; drawings attached by R2's attach_drawings.py
#                                                       # (PER_SOURCE, SOURCES and line tags as in experiments/r2/noon_models.sh)
# SPLIT rows: {"path": "data/... or /abs/path", "question": "...", "answer": ... (optional), "type"/"unit" (optional)}.
# The page (tab 1) then shows "Load N items: <LABEL>"; items without an answer get the expert's verdict as reference
# (questions.jsonl, origin audit -> `python -m stoa.eval --solver pipeline --split human`).
set -euo pipefail
IN=$1
NAME=${2:-stoa}
LABEL=${3:-"Stoa's example questions"}
cd "$(dirname "$0")/.."
PY=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
export JUNCTION_SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
mkdir -p "$JUNCTION_SHARED/logs/H"
if [ "${IN##*.}" = "txt" ]; then  # one question per line, no drawings: R2's attach_drawings.py picks dev drawings
  OUT="$JUNCTION_SHARED/artifacts/H/noon_$NAME.jsonl"
  "$PY" experiments/r2/attach_drawings.py "$(realpath "$IN")" --out "$OUT" --per-source "${PER_SOURCE:-2}" \
    ${SOURCES:+--sources "$SOURCES"}
  IN=$OUT
fi
if [ -f "$IN" ] && head -c 4000 "$IN" | grep -q '"solver"'; then
  PRED=$IN  # already a predictions file
elif [ ! -f "$IN" ] && [ -f "$JUNCTION_SHARED/artifacts/eval/${IN%.jsonl}.jsonl" ]; then
  PRED="$JUNCTION_SHARED/artifacts/eval/${IN%.jsonl}.jsonl"  # a run id
else
  SPLIT=$(realpath "$IN")
  PRED=$("$PY" -m stoa.eval --solver pipeline --split "$SPLIT" --no-leaderboard --note "workbench noon $NAME" 2>&1 \
    | tee -a "$JUNCTION_SHARED/logs/H/noon.log" | sed -n 's/^predictions: //p')
  [ -n "$PRED" ] || { echo "the eval run failed; see $JUNCTION_SHARED/logs/H/noon.log" >&2; exit 1; }
fi
"$PY" -m workbench.batch "$PRED" --name "$NAME" --label "$LABEL" --ref-label Stoa --n 500
echo "done: the workbench (tab 1) now offers '$LABEL'. Predictions: $PRED"
