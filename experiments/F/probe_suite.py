"""F's OPEN same-gold probe suite in one command: run every probe through a solver, then compare two suite runs.

All probe files live in $JUNCTION_SHARED/artifacts/F/ and are OPEN (dev drawings / open hard + hard2 bases): each row
re-asks a dataset question in another wording / language / scope word / file location with the SAME gold answer
(meta.kind = "<probe kind>:<wording>"). A change that helps Stoa's noon questions must not lose these.

    # run the suite on the current checkout (writes a manifest {probe: predictions file})
    PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/F/probe_suite.py run --tag mychange [--streams 3] [--workers 4]
        [--only apt_wording,neutral_path] [--solver pipeline]
    # compare with the end-of-night baseline (or any two manifests); lists lost rows per probe
    python3 experiments/F/probe_suite.py compare [BASE_MANIFEST] NEW_MANIFEST [--show 5]
    # record existing runs as a manifest (no evals): probe=RUN.jsonl pairs
    python3 experiments/F/probe_suite.py manifest --tag X apt_wording=/path/run.jsonl ...

Manifests: $JUNCTION_SHARED/artifacts/F/probe_suite/<tag>.json. Default baseline: BASELINE below (night 1a4e2af, c227).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
PROBE_DIR = SHARED / "artifacts" / "F"
SUITE_DIR = PROBE_DIR / "probe_suite"
BASELINE = SUITE_DIR / "night-1a4e2af.json"
# biggest first so the streams finish together
PROBES = ["apt_wording", "apt_wording_cc", "apt_wording_ml", "neutral_path", "comp_ml", "apt_wording_syn",
          "apt_wording_typo", "comp_ml_cc", "apt_wording_ml2", "this_plan", "this_plan_nh", "whole_top", "whole_top_nh",
          "apt_wording_ifc", "unit_probe", "format_swap", "apt_wording_scope", "apt_wording_scope_model",
          "apt_wording_scope_nh"]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _run_one(probe, solver, workers, note, py):
    cmd = [py, "-m", "stoa.eval", "--solver", solver, "--split", str(PROBE_DIR / f"{probe}.jsonl"),
           "--workers", str(workers), "--note", note]
    t0 = time.time()
    # the suite is a bulk run (10k rows): never let a solver reach Google's hackathon Gemini key (COMMON.md, Sat 10:50)
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    out = subprocess.run(cmd, capture_output=True, text=True, env=dict(env, PYTHONPATH="."))
    m = re.search(r"predictions: (\S+\.jsonl)", out.stdout + out.stderr)
    if not m:
        sys.stderr.write(f"[{probe}] no predictions file (exit {out.returncode}):\n{(out.stderr or out.stdout)[-800:]}\n")
        return probe, None
    print(f"[{probe}] {time.time() - t0:.0f} s -> {m.group(1)}", flush=True)
    return probe, m.group(1)


def cmd_run(args):
    probes = args.only.split(",") if args.only else [p for p in PROBES if (PROBE_DIR / f"{p}.jsonl").exists()]
    note = args.note or f"F probe_suite {args.tag}"
    manifest = {}
    with cf.ThreadPoolExecutor(args.streams) as ex:
        for probe, path in ex.map(lambda p: _run_one(p, args.solver, args.workers, note, sys.executable), probes):
            if path:
                manifest[probe] = path
    _write_manifest(args.tag, manifest)


def _write_manifest(tag, manifest):
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    dst = SUITE_DIR / f"{tag}.json"
    dst.write_text(json.dumps(manifest, indent=1))
    print(f"{len(manifest)} probes -> {dst}")


def cmd_manifest(args):
    _write_manifest(args.tag, dict(kv.split("=", 1) for kv in args.pairs))


def _stats(rows):
    sc = [r for r in rows if r.get("correct") is not None]
    ok = sum(1 for r in sc if r["correct"])
    cw = sum(1 for r in sc if not r["correct"] and (r.get("confidence") or 0) >= 0.8)
    return len(sc), ok, cw


def cmd_compare(args):
    base_path, new_path = (args.manifests if len(args.manifests) == 2 else [str(BASELINE), args.manifests[0]])
    base, new = json.loads(Path(base_path).read_text()), json.loads(Path(new_path).read_text())
    print(f"base {base_path}\nnew  {new_path}\n")
    print(f"{'probe':26s} {'n':>5s} {'acc base':>8s} {'acc new':>8s} {'cw base':>7s} {'cw new':>6s} {'won':>4s} {'lost':>4s}")
    tot = [0, 0, 0, 0, 0, 0, 0]
    lost_rows = []
    for probe in [p for p in PROBES if p in base and p in new] + sorted(set(base) & set(new) - set(PROBES)):
        a = {r["qid"]: r for r in _load(base[probe])}
        b = {r["qid"]: r for r in _load(new[probe])}
        common = [q for q in a if q in b and a[q].get("correct") is not None and b[q].get("correct") is not None]
        n, oka, cwa = _stats([a[q] for q in common])
        _, okb, cwb = _stats([b[q] for q in common])
        won = sum(1 for q in common if b[q]["correct"] and not a[q]["correct"])
        lost = [q for q in common if a[q]["correct"] and not b[q]["correct"]]
        lost_rows += [(probe, b[q]) for q in lost]
        for i, v in enumerate((n, oka, okb, cwa, cwb, won, len(lost))):
            tot[i] += v
        flag = "  <--" if lost or cwb > cwa else ""
        print(f"{probe:26s} {n:5d} {100 * oka / max(n, 1):8.1f} {100 * okb / max(n, 1):8.1f} {cwa:7d} {cwb:6d} {won:4d} "
              f"{len(lost):4d}{flag}")
    n = max(tot[0], 1)
    print(f"{'TOTAL':26s} {tot[0]:5d} {100 * tot[1] / n:8.1f} {100 * tot[2] / n:8.1f} {tot[3]:7d} {tot[4]:6d} {tot[5]:4d} "
          f"{tot[6]:4d}")
    if lost_rows and args.show:
        print(f"\nlost rows (first {args.show} per probe; OPEN probes, quote freely):")
        shown = {}
        for probe, r in lost_rows:
            if shown.get(probe, 0) >= args.show:
                continue
            shown[probe] = shown.get(probe, 0) + 1
            kind = (r.get("meta") or {}).get("kind", "")
            print(f"- [{probe} {kind}] {r['question'][:110]!r} gold {r.get('gold')} -> {r.get('value')} "
                  f"@{(r.get('confidence') or 0):.2f} {r.get('solver', '')} ({r['path'].split('/')[-1][:50]})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tag", required=True)
    r.add_argument("--solver", default="pipeline")
    r.add_argument("--streams", type=int, default=3)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--only", default="")
    r.add_argument("--note", default="")
    c = sub.add_parser("compare")
    c.add_argument("manifests", nargs="+", help="[BASE] NEW (default base: the end-of-night baseline)")
    c.add_argument("--show", type=int, default=5)
    m = sub.add_parser("manifest")
    m.add_argument("--tag", required=True)
    m.add_argument("pairs", nargs="+")
    args = ap.parse_args()
    {"run": cmd_run, "compare": cmd_compare, "manifest": cmd_manifest}[args.cmd](args)


if __name__ == "__main__":
    main()
