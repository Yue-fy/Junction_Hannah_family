#!/usr/bin/env bash
# D14 (S0 cycle 16): while a milestone driver (run_test.sh) is running, kill its dev/hard/hard2/hard2q evals as
# soon as they start, because F already ran those splits on equivalent code (night-F d764334 ≈ night 95f2277).
# The driver has no `set -e`, so it moves on to the next run (hard2p, hard2r, scorecard).
# Usage: setsid nohup bash experiments/s0/skip_dup_runs.sh "S0 sealed test 1 @ 95f2277" > log 2>&1 &
NOTE="$1"
END=$(( $(date +%s) + 4*3600 ))
while pgrep -f "run_test.sh" > /dev/null && [ "$(date +%s)" -lt "$END" ]; do
  for pid in $(pgrep -f -- "--note ${NOTE}: (dev|hard|hard2|hard2q)\$"); do
    echo "[$(date +%H:%M:%S)] killing duplicate run pid $pid: $(tr '\0' ' ' < /proc/$pid/cmdline | grep -o 'note.*')"
    kill "$pid"
  done
  sleep 15
done
echo "[$(date +%H:%M:%S)] driver gone; exit"
