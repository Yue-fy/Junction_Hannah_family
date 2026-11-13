"""Format-swap generality check: the same dev question asked on a sibling file of the same drawing (same answer).

The hidden test may hand us a PNG export instead of the PDF, or the SVG of an IFC plan. Answers must not change.
Swiss: pdf -> png, pdf -> dxf; ifc_models plans: pdf -> svg. Dev drawings only.

    PYTHONPATH=. python experiments/F/format_swap.py   -> $JUNCTION_SHARED/artifacts/F/format_swap.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/F/format_swap.jsonl
"""
import hashlib
import json
import random

from stoa.data import drawing_group, siblings
from stoa.eval.splits import load_split, shared_root

PLAN = {"swiss_dwellings": [(".png", 75), (".dxf", 75)], "ifc_models": [(".svg", 100)]}


def main():
    rng = random.Random(7)
    qs = [q for q in load_split("dev") if q.source in PLAN]
    rows = []
    for src, plan in PLAN.items():
        pool = [q for q in qs if q.source == src]
        rng.shuffle(pool)
        i = 0
        for ext, n in plan:
            k = 0
            while k < n and i < len(pool):
                q = pool[i]
                i += 1
                sib = siblings(q.path).get(ext)
                if not sib:
                    continue
                qid = "fs" + hashlib.sha1(f"{sib}\n{q.question}".encode()).hexdigest()[:10]
                rows.append({"qid": qid, "path": sib, "question": q.question, "answer": q.answer, "unit": q.unit,
                             "type": q.type, "source": src, "group": drawing_group(q.path),
                             "meta": {"kind": "format-swap", "recipe": f"{q.path.rsplit('.', 1)[-1]}->{ext[1:]}",
                                      "from_qids": [q.qid]}})
                k += 1
    out = shared_root() / "artifacts" / "F" / "format_swap.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(len(rows), out)


if __name__ == "__main__":
    main()
