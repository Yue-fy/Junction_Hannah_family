"""Compact view of results/leaderboard.jsonl.

    python -m stoa.eval.leaderboard [--split dev] [--all] [--source S] [--md]

Shows the newest full run (no --limit) per (solver, solver_args, filters) on the CURRENT split version
(split_hash), with weighted_acc, micro, macro, coverage, evidence rate, cost and hard kinds.
"""

from __future__ import annotations

import argparse
import json

from stoa.eval.splits import shared_root, split_hash


def rows(split: str | None, show_all: bool, source: str | None) -> list[dict]:
    out = {}
    lb = shared_root() / "results" / "leaderboard.jsonl"
    if not lb.exists():
        return []
    for line in open(lb, encoding="utf-8"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if split and r.get("split") != split:
            continue
        if not show_all:
            if r.get("limit") or r.get("split_hash") != split_hash(r.get("split", "")):
                continue
        if source and source not in (r.get("sources") or []):
            continue
        key = (r["solver"], json.dumps(r.get("solver_args") or {}, sort_keys=True), r.get("split"),
               json.dumps(r.get("sources")), json.dumps(r.get("types")), r.get("limit"))
        out[key if not show_all else (key, r["run_id"])] = r  # newest wins (file is append-only)
    return sorted(out.values(), key=lambda r: (r.get("split", ""), -(r["metrics"].get("weighted_acc") or 0)))


def fmt(x, pct=True):
    if x is None:
        return "-"
    return f"{100 * x:.1f}" if pct else f"{x}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.eval.leaderboard")
    ap.add_argument("--split", default=None)
    ap.add_argument("--all", action="store_true", help="include --limit runs, old split versions, all repeats")
    ap.add_argument("--source", default=None)
    a = ap.parse_args(argv)
    rs = rows(a.split, a.all, a.source)
    print("| time | split | solver | args / filters | n | weighted | micro | macro | cov | evid | $/1k Q | hard: transl/para/comp | commit | note |")
    print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|")
    for r in rs:
        m = r["metrics"]
        args = ", ".join(f"{k}={v}" for k, v in (r.get("solver_args") or {}).items())
        filt = " ".join(x for x in [f"src={','.join(r['sources'])}" if r.get("sources") else "",
                                    f"type={','.join(r['types'])}" if r.get("types") else "",
                                    f"limit={r['limit']}" if r.get("limit") else ""] if x)
        hk = m.get("by_kind") or {}
        hard = "/".join(fmt((hk.get(k) or {}).get("accuracy")) for k in ("translation", "paraphrase", "composition")) if hk else ""
        print(f"| {r['time'][11:16]} | {r['split']} | {r['solver']} | {(args + ' ' + filt).strip()} | {r['n']} | "
              f"{fmt(m.get('weighted_acc'))} | {fmt(m.get('accuracy'))} | {fmt(m.get('macro_accuracy'))} | "
              f"{fmt(m.get('coverage'))} | {fmt(m.get('evidence_rate'))} | {m.get('usd_per_1k_q', '-')} | {hard} | "
              f"{r.get('commit', '')} | {(r.get('note') or '')[:50]} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
