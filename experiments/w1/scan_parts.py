"""Which non-test IFC models have elements nested under a parent of the same class (S0 D15 mechanism A)?"""
import collections
import json
import sys
from pathlib import Path

from stoa.solvers.ifc.index import nested_parts

D = Path("/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset/data")
test_models = set()
for l in open("/home/fangy4/work/projects/junction-shared/results/splits/test.jsonl"):
    r = json.loads(l)
    if "ifc" in r.get("path", ""):
        test_models.add(r["path"].split("/")[-1].split("_")[0])
for sub in sys.argv[1:]:
    for f in sorted((D / sub).glob("*.ifc")):
        if f.name.split("_")[0] in test_models or "molio" in f.name:
            continue
        if f.stat().st_size > 60e6:
            continue
        try:
            parts = nested_parts(f"data/{sub}/{f.name}")
        except Exception as e:  # noqa: BLE001
            print(f.name, "ERR", e)
            continue
        c = collections.Counter(parts.values())
        print(f.name, len(parts), dict(c.most_common(5)), flush=True)
