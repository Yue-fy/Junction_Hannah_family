"""Re-ask every row of an IFC plan-sheet probe on the sheet's IFC MODEL path (stoa.data.ifc_model_for), so a storey
reference has to be resolved instead of being implied by the sheet. Kinds get the prefix 'scopeM_'.

    python experiments/F/model_path_variant.py IN.jsonl OUT.jsonl
    (c225: artifacts/F/apt_wording_scope.jsonl -> artifacts/F/apt_wording_scope_model.jsonl)
"""
import json
import sys

from stoa.data import dataset_rel, ifc_model_for

src, dst = sys.argv[1], sys.argv[2]
out = []
for line in open(src):
    r = json.loads(line)
    m = ifc_model_for(r["path"])
    if not m or dataset_rel(str(m)) == r["path"]:
        continue
    d = dict(r, path=dataset_rel(str(m)), qid=r["qid"] + "M")
    d["meta"] = dict(r["meta"], kind=r["meta"]["kind"].replace("scope_", "scopeM_"),
                     probe_kind=r["meta"]["probe_kind"].replace("scope_", "scopeM_"))
    out.append(d)
with open(dst, "w", encoding="utf-8") as f:
    for d in out:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
print(len(out), "rows ->", dst)
