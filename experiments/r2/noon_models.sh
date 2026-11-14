#!/usr/bin/env bash
# Noon reveal, model side (R2). Stoa's example questions in eval-split format (path, question, answer|null, type,
# meta.kind) -> the team pipeline, the plain local VLM (vlm_direct, the "just ask a VLM" baseline) and hosted
# Nemotron 3.5 Super VL (vlm_direct backend=nvidia; 1 worker, first N questions: rate limits + credits), each graded
# the same way (numbers exact/2%, text by the local LLM judge), then one per-kind table with cost.
# usage: experiments/r2/noon_models.sh SPLIT.jsonl [NEMOTRON_LIMIT=40] [GEMINI_LIMIT=0]
# GEMINI_LIMIT > 0 adds hosted Gemini (vlm_direct backend=gemini, $GEMINI_MODEL or gemini-3-flash-preview) on the first
# N questions: 1 worker, counted against the per-agent daily cap (llm.py; Google's no-abuse rule, COMMON.md).
set -euo pipefail
SPLIT=$1
NV=${2:-40}
GL=${3:-0}
cd "$(dirname "$0")/../.."
PY=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
export JUNCTION_SHARED=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
run() {  # prints the predictions file of one eval run
  "$PY" -m stoa.eval --split "$SPLIT" --judge local --note "noon_models $(basename "$SPLIT")" "$@" 2>&1 \
    | tee -a "$JUNCTION_SHARED/logs/R2/noon_models.log" | sed -n 's/^predictions: //p'
}
mkdir -p "$JUNCTION_SHARED/logs/R2"
P=$(run --solver pipeline --workers 4)
V=$(run --solver vlm_direct --workers 4)
N=$(run --solver vlm_direct --solver-arg backend=nvidia --workers 1 --limit "$NV")
echo "pipeline: $P"; echo "vlm_direct (local 8B): $V"; echo "vlm_direct (hosted Nemotron, first $NV): $N"
if [ "$GL" -gt 0 ]; then
  G=$(STOA_AGENT=${STOA_AGENT:-R2} STOA_GEMINI_PURPOSE="noon reveal: Stoa example kinds, first $GL" \
      run --solver vlm_direct --solver-arg backend=gemini --workers 1 --limit "$GL")
  echo "vlm_direct (hosted Gemini, first $GL): $G"
  "$PY" experiments/r2/compare_runs.py "$P" "$V" "$G" --by kind
fi
"$PY" experiments/r2/compare_runs.py "$P" "$V" --by kind
echo "--- on the Nemotron subset:"
"$PY" experiments/r2/compare_runs.py "$P" "$V" "$N" --by kind
# every question with each model's answer @ confidence (rows without gold are shown, not scored)
SBS="$JUNCTION_SHARED/artifacts/R2/noon_side_by_side_$(basename "$SPLIT" .jsonl).txt"
"$PY" experiments/r2/compare_runs.py "$P" "$V" --by kind --show > "$SBS"
echo "side by side (pipeline vs local VLM, all questions): $SBS"
