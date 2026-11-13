"""Drop-in adapter for W3/W4: CC5K-model symbol counts as contract Answers ("raster_cc5k").

    from experiments.r1.cc5k_model.adapter import RasterCC5K   # or sys.path-insert this folder
    s = RasterCC5K()
    s.can_handle(path, question)  # cubicasa-style raster + windows/doors/WC seats/sinks question (EN or FI)
    s.solve(path, question)       # Answer(value=count, evidence=[one image_px box per symbol], confidence, ...)

Lookup order: (1) precomputed counts in $JUNCTION_SHARED/artifacts/R1/cc5k_counts.jsonl (all 4,787 dataset
drawings), (2) live CPU inference via predict.py in an env with torch (CC5K_PYTHON, default junction-train),
~1-3 s per drawing, no GPU, no LLM tokens.
Leak note (DECISIONS D3): the model saw the original CubiCasa5K train list; report accuracy on cc5k_heldout only.
Answers on a drawing from that list carry an assumption line that says so.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
CACHE = os.path.join(SHARED, "artifacts", "R1", "cc5k_counts.jsonl")
PY = os.environ.get("CC5K_PYTHON", "/data/User/fangy4/envs/junction-train/bin/python")
TEMPLATES = {  # EN + FI wordings of the dataset; W4's intent parser can call answer_template() directly
    "windows": r"\bwindows?\b|ikkun",
    "doors": r"\bdoors?\b|\bovea\b|\bovet\b|\bovia\b",
    "wc_seats": r"toilet bowl|wc seat|wc-istuin",
    "sinks": r"\bsinks?\b|wash ?basin|pesu- ja tiskiallas|pesuallas|tiskiallas",
}
NOUN = {"windows": "window", "doors": "door", "wc_seats": "toilet", "sinks": "sink / wash basin"}
_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = {}
        if os.path.exists(CACHE):
            for line in open(CACHE):
                d = json.loads(line)
                _cache[d["path"]] = d
    return _cache


def template_of(question):
    q = question.lower()
    if re.search(r"shower|bathtub|suihku|kylpyamme", q):
        return None  # no shower class in the model → leave to the prior
    for t, rx in TEMPLATES.items():
        if re.search(rx, q):
            return t
    return None


def counts_for(path):
    """Return the cached/live record {"counts": {...}, "cc5k_list": ...} for a dataset-relative or absolute path."""
    rel = path if path.startswith("data/") else os.path.relpath(path, DATA)
    d = _load().get(rel)
    if d is not None:
        return d
    full = path if os.path.isabs(path) else os.path.join(DATA, path)
    out = subprocess.run([PY, "-I", os.path.join(HERE, "predict.py"), full], capture_output=True, text=True, timeout=300)
    d = json.loads(out.stdout.strip().splitlines()[-1])
    d.update(path=rel, cc5k_list="unknown", live=True)
    _load()[rel] = d
    return d


ROOM_KEYS = {"bedroom": "bedrooms", "balcony": "balconies", "bathroom": "bathrooms", "kitchen": "kitchens",
             "window": "windows", "door": "doors", "wc": "wc_seats", "toilet": "wc_seats", "sink": "sinks"}
# P(the other answer is right | agrees / disagrees with the segmentation), cc5k_heldout, pipeline night cbd2fe8
AGREE_ACC = {"bedrooms": (0.75, 0.37), "balconies": (0.92, 0.65), "bathrooms": (0.96, 0.82), "kitchens": (0.96, 0.80)}


def cross_check(path, concept, value, source="label reading"):
    """Independent check of another solver's count with the CC5K segmentation. concept: bedroom|balcony|
    bathroom|kitchen|window|door|wc|sink. Returns (agrees: bool|None, line) with a line in the D4/W5 format
    ("cross-check: label reading 3 = CC5K room segmentation 3 ✓" or "... ≠ ... ✗")."""
    key = ROOM_KEYS.get(concept)
    if key is None:
        return None, ""
    d = counts_for(path)
    rec = (d.get("rooms") or {}).get(key) or d["counts"].get(key)
    if rec is None:
        return None, ""
    seg = rec["count"]
    what = "CC5K room segmentation" if key in AGREE_ACC else "CC5K symbol segmentation"
    ok = int(value) == seg if value is not None else None
    return ok, f"cross-check: {source} {value} {'=' if ok else '≠'} {what} {seg} {'✓' if ok else '✗'}"


class RasterCC5K:
    name = "raster_cc5k"

    def can_handle(self, path, question):
        return path.lower().endswith((".png", ".jpg", ".jpeg")) and template_of(question) is not None

    def solve(self, path, question):
        from stoa.contract import Answer, Evidence  # imported lazily so this file runs without the stoa package
        t0 = time.time()
        t = template_of(question)
        if t is None:
            return Answer.abstain(self.name, "not a windows/doors/WC seats/sinks question")
        return self.answer_template(path, t, t0)

    def answer_template(self, path, t, t0=None):
        from stoa.contract import Answer, Evidence
        t0 = t0 or time.time()
        d = counts_for(path)
        c = d["counts"][t]
        rel = d["path"]
        ev = [Evidence(file=rel, bbox=[float(v) for v in b], bbox_space="image_px", note=f"{NOUN[t]} {i + 1}")
              for i, b in enumerate(c["boxes"])]
        assumptions = ["symbols segmented by the pretrained CubiCasa5K model (Kalervo et al. 2019); "
                       "each box is one counted symbol"]
        if d.get("cc5k_list") == "train":
            assumptions.append("this drawing is in the model's original training list: the count may be memorised")
        missing = []
        if c["confidence"] < 0.5:
            missing.append(f"a second independent count of {NOUN[t]} symbols (model exact on ~{c['confidence']:.0%} "
                           f"of held-out drawings with this count; usually within ±1–2)")
        return Answer(value=c["count"], unit="count", confidence=c["confidence"], evidence=ev, solver=self.name,
                      trace=[f"raster_cc5k: {c['count']} {NOUN[t]} components ({'live' if d.get('live') else 'cached'})"],
                      assumptions=assumptions, missing=missing)


if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))
    s = RasterCC5K()
    a = s.solve(sys.argv[1], " ".join(sys.argv[2:]))
    print(a.model_dump_json(indent=1)[:1500])
