"""Trigger + output checks for estimate.py on wordings R1 did not write.

  make   : the local LLM rewrites each SEED (out-of-drawing question, should fire) and each NEG (states its own rate /
           constant = derived quantity, must NOT fire) 3x in English + once in 8 languages -> probe_para.jsonl
  score  : recall on the paraphrases split by ORIGINAL seed (A = tuning half, B = held out), false fires on the NEG
           paraphrases, on all 127,044 dataset questions, the open splits, W4's derived probes, F's open probes and
           Q's red-team rows that are not 'unanswerable'; then solve() on every fired positive: value, unit, conf < 0.5,
           an assumption and a missing line (Q's handled_flag), 0 LLM calls.

    python experiments/r1/estimate/probe.py make|score [--show A|B|neg]
"""
import glob
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.estimate.estimate import kind_of, solve  # noqa: E402

H = Path(__file__).parent
OUT = H / "probe_para.jsonl"
SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
CC = "data/cubicasa5k/high_quality-5968.png"
CC2 = "data/cubicasa5k/high_quality_architectural-11369.png"
SW = "data/swiss_dwellings/site1024_bldg2107_floor9518.pdf"
SW2 = "data/swiss_dwellings/site1798_bldg2895_floor13257.pdf"
IFC = "data/ifc_models/bimspeed-warmond_ar_plan-05-2-level.pdf"
HABS = "data/habs/ak0040_sheet_00001.jpg"
FIN = "data/finna/hka.139877668752900_168422869617700.jpg"
SEEDS = [  # (kind, path, question)
    ("occupants", CC, "How many people live in this apartment?"),
    ("occupants", SW, "How many residents does apartment B have?"),
    ("occupants", IFC, "How many people could this building accommodate?"),
    ("occupants", CC2, "What is the likely household size for this flat?"),
    ("rent", CC2, "What is the monthly rent of this apartment in euros?"),
    ("rent", SW, "How much rent would apartment C fetch per month?"),
    ("price", CC, "What is this apartment worth on the market?"),
    ("price", SW2, "What would be the sale price of this flat?"),
    ("construction_cost", IFC, "What did this building cost to construct, in euros?"),
    ("construction_cost", SW, "Estimate the construction cost of this floor."),
    ("construction_cost", HABS, "How much did it cost to build this structure?"),
    ("u_value", SW2, "What is the U-value of the exterior walls in W/m²K?"),
    ("u_value", HABS, "How well insulated are the outer walls (thermal transmittance)?"),
    ("year_built", CC, "What year was this building constructed?"),
    ("year_built", FIN, "When was this house built?"),
    ("year_built", HABS, "How old is this building?"),
    ("energy", CC2, "How much heating energy does this apartment use per year?"),
    ("energy", IFC, "What is the annual energy consumption of this building in kWh?"),
]
NEG = [  # states its own rate / constant -> derived quantity, answered exactly elsewhere
    (CC, "If each person needs 12 m² of floor area, how many people can live in this apartment?"),
    (CC2, "At a rent of 15 euros per square metre per month, what is the monthly rent of this apartment?"),
    (SW, "If the flat sells for 6,000 CHF per m², what is the sale price of apartment B?"),
    (IFC, "Construction costs 2,800 euros per m² of room area: what did the rooms on this storey cost?"),
    (SW2, "With a heating demand of 90 kWh per m² per year, what is the annual energy use of apartment A?"),
    (CC, "Each resident needs 25 m²; how many residents fit in this flat?"),
]
LANGS = {"fi": "Finnish", "de": "German", "fr": "French", "it": "Italian", "sv": "Swedish", "nl": "Dutch",
         "et": "Estonian", "es": "Spanish"}


def make():
    from stoa.llm import chat, extract_json

    items = [("pos", i, k, p, q) for i, (k, p, q) in enumerate(SEEDS)] + \
            [("neg", i, None, p, q) for i, (p, q) in enumerate(NEG)]

    def para(it):
        tag, i, k, p, q = it
        prompt = (f"Rewrite this question about a building in 3 different ways a home buyer, an engineer or a hackathon "
                  f"judge might type it (vary words and sentence shape; same meaning; keep every number and unit). "
                  f"Then translate the ORIGINAL into {', '.join(LANGS.values())}, the way a native speaker would ask "
                  f"it. JSON: {{\"en\": [3 strings], " + ", ".join(f'"{x}": string' for x in LANGS) +
                  "}\n\nQuestion: " + q)
        js = extract_json(chat(prompt, max_tokens=900, temperature=0.0).text) or {}
        out = [("orig", 0, q)] + [("en", j, x) for j, x in enumerate((js.get("en") or [])[:3])] + \
              [(x, 0, js[x]) for x in LANGS if isinstance(js.get(x), str)]
        return [{"qid": f"{tag}{i}-{lang}{j}", "path": p, "question": s.strip(), "type": "other",
                 "meta": {"set": tag, "seed": f"{tag}{i}", "kind": k, "lang": lang, "orig": q}}
                for lang, j, s in out if isinstance(s, str) and s.strip()]

    with ThreadPoolExecutor(8) as ex:
        rows = [r for rs in ex.map(para, items) for r in rs]
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows ({sum(r['meta']['set'] == 'pos' for r in rows)} pos) -> {OUT}")


def _other_questions():
    """(name, question) of everything that must NOT fire."""
    for line in open(os.environ["STOA_DATA"] + "/questions.jsonl"):
        yield "dataset", json.loads(line)["question"]
    for f in sorted(glob.glob(str(SHARED / "results/splits/*.jsonl"))):
        if f.endswith(("test.jsonl", "hard2q.jsonl", "hard2p.jsonl", "hard2r.jsonl", "hard3.jsonl")):
            continue
        for line in open(f):
            r = json.loads(line)
            if "question" in r:
                yield Path(f).name, r["question"]
    for f in sorted(glob.glob(str(SHARED / "artifacts/W4/derived*.jsonl")) + glob.glob(str(SHARED / "artifacts/F/*.jsonl"))):
        for line in open(f):
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(r, dict) and isinstance(r.get("question"), str):
                yield Path(f).name, r["question"]
    try:
        txt = subprocess.run(["git", "show", "night-Q:redteam/questions.jsonl"], cwd=ROOT, capture_output=True,
                             text=True).stdout
        for line in txt.splitlines():
            r = json.loads(line)
            if (r.get("meta") or {}).get("kind") != "unanswerable":
                yield "redteam", r["question"]
    except Exception:  # noqa: BLE001
        pass


def score():
    show = sys.argv[sys.argv.index("--show") + 1] if "--show" in sys.argv else None
    rows = [json.loads(x) for x in open(OUT)]
    pos = [r for r in rows if r["meta"]["set"] == "pos"]
    seeds = sorted({r["meta"]["seed"] for r in pos}, key=lambda s: int(s[3:]))
    half_a = set(seeds[0::2])
    for name, rs in (("A (tuning)", [r for r in pos if r["meta"]["seed"] in half_a]),
                     ("B (held out)", [r for r in pos if r["meta"]["seed"] not in half_a])):
        by = defaultdict(lambda: [0, 0])
        for r in rs:
            k = kind_of(r["question"])
            ok = k["fire"] and k["kind"] == r["meta"]["kind"]
            for key in (r["meta"]["lang"], "ALL"):
                by[key][0] += 1
                by[key][1] += ok
            if show and name.startswith(show) and not ok:
                print("  miss", r["meta"]["kind"], r["meta"]["lang"], "|", r["question"][:130], "|", k["kind"])
        print(name, "  ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(by.items())))
    neg = [r for r in rows if r["meta"]["set"] == "neg"]
    nf = [r for r in neg if kind_of(r["question"])["fire"]]
    print(f"stated-rate paraphrases fired (should be 0): {len(nf)}/{len(neg)}")
    if show == "neg":
        for r in nf:
            print("  NEG FIRE", r["meta"]["lang"], "|", r["question"][:130])
    by, n = defaultdict(int), defaultdict(int)
    for src, q in _other_questions():
        n[src] += 1
        if kind_of(q)["fire"]:
            by[src] += 1
            if by[src] <= 3:
                print("  FALSE FIRE", src, "|", q[:130])
    print("false fires:", sum(by.values()), "/", sum(n.values()), dict(by))
    # outputs on every fired positive
    good, tot, calls = 0, 0, 0
    for r in pos:
        k = kind_of(r["question"])
        if not k["fire"]:
            continue
        a = solve(r["path"], r["question"], k)
        tot += 1
        calls += a.cost.llm_calls if a else 0
        ok = a is not None and isinstance(a.value, (int, float)) and a.confidence < 0.5 and a.missing and a.assumptions
        good += bool(ok)
    print(f"solve() on fired positives: {good}/{tot} give a number + conf < 0.5 + assumptions + missing; LLM calls {calls}")


if __name__ == "__main__" and sys.argv[1] in ("make", "score"):
    {"make": make, "score": score}[sys.argv[1]]()


def front_end():
    """Recall when the trigger also runs on the pipeline's English translation (as the link route does)."""
    from stoa.llm import to_english

    rows = [json.loads(x) for x in open(OUT) if json.loads(x)["meta"]["set"] == "pos"]
    seeds = sorted({r["meta"]["seed"] for r in rows}, key=lambda s: int(s[3:]))
    half_a = set(seeds[0::2])

    def run(r):
        k = kind_of(r["question"])
        ok = k["fire"] and k["kind"] == r["meta"]["kind"]
        if not ok and r["meta"]["lang"] not in ("en", "orig"):
            t = to_english(r["question"], force=True)
            q = t if isinstance(t, str) else getattr(t, "text", None) or (t[0] if isinstance(t, tuple) else str(t))
            k2 = kind_of(q)
            ok = k2["fire"] and k2["kind"] == r["meta"]["kind"]
        return r, ok

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(run, rows))
    for name, sel in (("A", lambda r: r["meta"]["seed"] in half_a), ("B", lambda r: r["meta"]["seed"] not in half_a)):
        rs = [(r, ok) for r, ok in res if sel(r)]
        print(f"{name} asked-or-translated: {sum(ok for _, ok in rs)}/{len(rs)}; non-English "
              f"{sum(ok for r, ok in rs if r['meta']['lang'] not in ('en', 'orig'))}/"
              f"{sum(1 for r, _ in rs if r['meta']['lang'] not in ('en', 'orig'))}")


if __name__ == "__main__" and sys.argv[1] == "front_end":
    front_end()
