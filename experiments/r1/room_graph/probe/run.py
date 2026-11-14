"""Room-graph probe: answer per-room / relational questions from graph_text(room_graph(path)) with the local LLM.

Usage (repo root):
  python experiments/r1/room_graph/probe/run.py answer PROBE.jsonl --mode graph|graph_img|img|solve [--out OUT.jsonl]
  python experiments/r1/room_graph/probe/run.py score PROBE.jsonl PRED.jsonl [PRED.jsonl ...]

`answer` writes one JSON line per question {qid, value, unit, room, raw, tokens_in, tokens_out, seconds}.
`score` accepts our own outputs and stoa.eval prediction files (artifacts/eval/*-questions-*.jsonl or any jsonl with
qid + value/pred). Gold was written BY EYE before any method ran (probe_v1.jsonl meta.gold_how).
Scoring: count exact; area within 2%; text = an accepted name (meta.accept) appears as a word in the answer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

SYSTEM = ("You answer questions about one apartment floor plan. Room names on Finnish plans: MH/AH/H = bedroom, "
          "OH = living room, K/KT/KK/KEITTIÖ = kitchen, KPH/KH/PH/PESUH = bathroom/washroom, S/L.H./SAUNA = sauna, "
          "WC = toilet room, ET/ETEINEN = entrance hall, VH/HV/VAR = closet/storage, PARV/PARVEKE = balcony, "
          "TK = vestibule, RT = dining, SUIHKU = shower room. Reply with JSON only: "
          '{"value": <a number, or a short text answer that names rooms by their type and printed label, e.g. '
          '"bathroom (KPH)", never by an id like R3>, "unit": <"count"|"m2"|null>, "room": <room id(s) used or null>, '
          '"why": <one short sentence>}.')

PRINTED = True

GRAPH_NOTE = ("The room graph below was extracted automatically from the plan image (CubiCasa5K segmentation). "
              "'doors to' lists the rooms a door connects (an apartment's hall may be split into an 'entry' room and "
              "parts of other rooms); the quoted text is the label printed in that room; areas are rough estimates "
              "from door widths, so prefer printed areas when you can read them.")


def _graph(path: str) -> str:
    from experiments.r1.room_graph.graph import graph_text, room_graph
    return graph_text(room_graph(path, printed=PRINTED))


def answer_one(row: dict, mode: str) -> dict:
    from stoa import llm
    if mode == "solve":  # the wire-ready function (experiments/r1/room_graph/answer.py)
        from experiments.r1.room_graph.answer import solve
        t = time.time()
        with llm.cost_meter() as c:
            a = solve(row["path"], row["question"])
        return {"qid": row["qid"], "value": a.value, "unit": a.unit, "confidence": a.confidence,
                "evidence": len(a.evidence), "trace": a.trace, "assumptions": a.assumptions, "missing": a.missing,
                "tokens_in": c.llm_tokens_in, "tokens_out": c.llm_tokens_out, "seconds": round(time.time() - t, 2),
                "mode": mode}
    from stoa.data import abspath
    path = row["path"]
    t = time.time()
    parts = []
    if mode in ("graph", "graph_img"):
        parts.append(GRAPH_NOTE + "\n\n" + _graph(path))
    parts.append("Question: " + row["question"])
    images = None
    if mode in ("graph_img", "img"):
        images = [str(abspath(path))]
    res = llm.chat("\n\n".join(parts), images=images, system=SYSTEM, max_tokens=200, cache=True)
    try:
        js = llm.extract_json(res.text) or {}
        if isinstance(js, list):
            js = js[0] if js and isinstance(js[0], dict) else {}
    except Exception:  # noqa: BLE001
        js = {}
    return {"qid": row["qid"], "value": js.get("value"), "unit": js.get("unit"), "room": js.get("room"),
            "why": js.get("why"), "raw": res.text[:400], "tokens_in": res.prompt_tokens,
            "tokens_out": res.completion_tokens, "seconds": round(time.time() - t, 2), "mode": mode}


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(x))
    return float(m.group().replace(",", ".")) if m else None


def correct(row: dict, value) -> bool:
    t, gold = row["type"], row["answer"]
    if t == "count":
        x = _num(value)
        return x is not None and int(round(x)) == int(gold)
    if t == "area":
        x = _num(value)
        return x is not None and abs(x - gold) <= 0.02 * abs(gold)
    s = " " + re.sub(r"[^a-zäöå0-9/.]+", " ", str(value or "").lower()) + " "
    for a in row["meta"].get("reject", []):  # the answer names a different room that shares the type word
        if re.search(r"(?<![a-zäöå])" + re.escape(a.lower()) + r"(?![a-zäöå])", s):
            return False
    for a in row["meta"]["accept"]:
        if re.search(r"(?<![a-zäöå])" + re.escape(a.lower()) + r"(?![a-zäöå])", s):
            return True
    return False


def load_preds(p: str) -> dict:
    out = {}
    for line in open(p):
        r = json.loads(line)
        q = r.get("qid")
        if q is None:
            continue
        v = r.get("value", r.get("pred", r.get("pred_value")))
        if isinstance(v, dict):
            v = v.get("value")
        out[q] = v
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["answer", "score"])
    ap.add_argument("probe")
    ap.add_argument("preds", nargs="*")
    ap.add_argument("--mode", default="graph", choices=["graph", "graph_img", "img", "solve"])
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    rows = [json.loads(line) for line in open(a.probe)]
    if a.cmd == "answer":
        out = a.out or str(Path(a.probe).with_name(f"pred_{a.mode}.jsonl"))
        with ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(lambda r: answer_one(r, a.mode), rows))
        with open(out, "w") as f:
            for r in res:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        ok = sum(correct(r, p["value"]) for r, p in zip(rows, res))
        tin = sum(p["tokens_in"] or 0 for p in res) / len(res)
        print(f"{a.mode}: {ok}/{len(rows)} right; mean tokens in {tin:.0f}; -> {out}")
        return
    names = [Path(p).stem[-28:] for p in a.preds]
    preds = [load_preds(p) for p in a.preds]
    print("qid    type   gold            " + "  ".join(f"{n[-12:]:>12}" for n in names))
    tot = [0] * len(preds)
    by = {}
    for r in rows:
        cells = []
        for i, pr in enumerate(preds):
            v = pr.get(r["qid"])
            ok = correct(r, v)
            tot[i] += ok
            by.setdefault((r["type"], i), []).append(ok)
            cells.append(f"{('✓' if ok else '✗') + ' ' + str(v)[:10]:>12}")
        print(f"{r['qid']} {r['type']:6} {str(r['answer'])[:14]:15} " + "  ".join(cells))
    print("total  " + "  ".join(f"{n[-12:]}: {t}/{len(rows)}" for n, t in zip(names, tot)))
    for t in ("count", "area", "text"):
        print(f"  {t:5} " + "  ".join(f"{sum(by.get((t, i), []))}/{len(by.get((t, i), []))}" for i in range(len(preds))))


if __name__ == "__main__":
    main()
