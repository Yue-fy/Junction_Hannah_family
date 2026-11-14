"""A/B of _TR_HINTS2 (F 08:20 open-set slips) on concept match: hardL_open, lang4, belek, W4's lang4b. Owner: R2."""
import collections, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import stoa.llm as L  # noqa: E402
from stoa.router.intent import parse  # noqa: E402
S = Path("/home/fangy4/work/projects/junction-shared")
rows = [json.loads(x) for x in (S / "results/splits/hardL_open.jsonl").open()]
en = {r["meta"]["base_qid"]: r["question"] for r in rows if r["meta"]["lang"] == "en"}
sets = [("hardL_open", [(r["question"], en[r["meta"]["base_qid"]], r["meta"]["lang"]) for r in rows
                        if r["meta"]["lang"] != "en" and r["meta"]["base_qid"] in en])]
l4 = [json.loads(x) for x in (S / "artifacts/R2/lang4.jsonl").open()]
l4en = {json.loads(x)["qid"].split("-")[0]: json.loads(x)["question"] for x in (S / "artifacts/R2/lang4_en.jsonl").open()}
sets.append(("lang4", [(r["question"], l4en[r["qid"].split("-")[0]], r["meta"]["lang"]) for r in l4]))
key = lambda q: (parse(q).task, parse(q).target)  # noqa: E731
base = L._TR_GLOSSARY
for name, items in sets:
    for tag, g in [("v3", base), ("v3+hints2", base + L._TR_HINTS2)]:
        L._TR_GLOSSARY = g; L._tr_memo.clear()
        with ThreadPoolExecutor(4) as ex:
            tr = list(ex.map(lambda it: L.to_english(it[0], force=True), items))
        m = [key(t.text) == key(e) for t, (_, e, _) in zip(tr, items)]
        bl = collections.defaultdict(lambda: [0, 0])
        for x, (_, _, lg) in zip(m, items):
            bl[lg][0] += x; bl[lg][1] += 1
        print(f"{name:10s} {tag:10s} {sum(m)}/{len(m)} not ok {sum(not t.ok for t in tr)} "
              + " ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(bl.items())), flush=True)
        if "--show" in sys.argv and tag != "v3":
            for t, (q, e, lg), x in zip(tr, items, m):
                if not x:
                    print(f"   MISS {lg}: {t.text[:90]} | {key(t.text)} vs {key(e)}")
L._TR_GLOSSARY = base
