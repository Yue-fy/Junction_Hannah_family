"""All 800 CubiCasa dev questions asked on the dataset path AND on the same PNG saved the way the demo's upload saves
it (<dir>/<sha256[:12]>/plan.png, web/mock/stoaApi.ts saveUpload, no style): the upload penalty, paired, at dev size.

    PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/q/upload_dev.py   # -> $JUNCTION_SHARED/artifacts/Q/upload_dev.jsonl
"""
import hashlib
import json
import os
from pathlib import Path

from stoa.data import abspath, make_qid

S = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
UP = S / "artifacts/Q/redteam/img/uploads_dev"
dev = {json.loads(l)["qid"] for l in open(S / "results/splits/dev.jsonl")}
out = []
for line in open(Path(os.environ["STOA_DATA"]) / "questions.jsonl", encoding="utf-8"):
    d = json.loads(line)
    if not d["path"].startswith("data/cubicasa5k/") or make_qid(d["path"], d["question"]) not in dev:
        continue
    body = abspath(d["path"]).read_bytes()
    dst = UP / hashlib.sha256(body).hexdigest()[:12] / "plan.png"
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(body)
    for path, kind in ((d["path"], "control"), (str(dst), "upload")):
        out.append({"qid": "ud" + make_qid(path, d["question"])[:10], "path": path, "question": d["question"],
                    "answer": d["answer"], "unit": d.get("unit"), "type": d.get("type"),
                    "meta": {"kind": f"updev:{kind}", "expect": "same", "base": d["path"]}})
with open(S / "artifacts/Q/upload_dev.jsonl", "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(out), "rows")
