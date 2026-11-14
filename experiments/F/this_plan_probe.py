"""'This floor plan' probe (F c226): dev ifc_models sheet questions that name the sheet's own storey, re-asked without
the storey name ("on the floor plan of 'EG'" -> "on this floor plan"). Same gold when the sheet IS that storey's plan
(the control run on the dataset path shows it). Then neutralize.py --mode hash re-asks them on hashed sheet names:
does the solver find the sheet's storey from the drawing, or only from its file name? OPEN probe (dev drawings).

    python experiments/F/this_plan_probe.py      # -> $JUNCTION_SHARED/artifacts/F/this_plan.jsonl
    python experiments/F/neutralize.py $A/this_plan.jsonl $A/this_plan_nh.jsonl --mode hash
"""
from __future__ import annotations

import hashlib
import json
import re

from stoa.eval.splits import load_split, shared_root

WORDINGS = [  # (regex on the dataset question with group 's' = storey, replacement)
    (r"on the floor plan of '(?P<s>[^']+)'", "on this floor plan"),
    (r"on '(?P<s>[^']+)'", "on this floor"),
]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main() -> None:
    rows = []
    for q in load_split("dev"):
        if q.source != "ifc_models" or q.answer is None or not q.path.endswith(".pdf"):
            continue
        stem = q.path.rsplit("/", 1)[-1][:-4].lower()
        for rx, rep in WORDINGS:
            m = re.search(rx, q.question)
            if not m:
                continue
            st = m.group("s")
            if not re.search(r"_plan-\d+-" + re.escape(_norm(st)) + r"$", stem) or st.startswith("-"):
                break  # not this sheet's own storey (or '-1' vs '1' ambiguity in file names)
            new = q.question[: m.start()] + rep + q.question[m.end():]
            for wording, text in (("dataset", q.question), ("this", new)):
                qid = "tp" + hashlib.sha1(f"{q.qid}|{wording}".encode()).hexdigest()[:10]
                rows.append({"qid": qid, "path": q.path, "question": text, "answer": q.answer, "unit": q.unit,
                             "type": q.type, "meta": {"kind": f"this_{q.type}:{wording}", "wording": wording,
                                                      "probe_kind": "this_plan", "base_qid": q.qid}})
            break
    out = shared_root() / "artifacts" / "F" / "this_plan.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
