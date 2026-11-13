"""raster — counting on raster floor plans (cubicasa5k PNGs, any PNG/JPG drawing). Owner: W3.

Pipeline per question:
  1. question -> object class (classes.question_class; EN + FI + a few other languages).
  2. method chosen per class by a GATE measured on a TRAIN sample (experiments/w3/calibrate.py ->
     stoa/solvers/raster/gate.json), never on dev:
       labels  room-name labels read by the VLM once per image (shared by all questions on that image),
               mapped to classes with Finnish plan abbreviations (MH, KH, PH, S, WC, PARV, ...); count them
       points  the VLM points at each symbol (window, door, toilet, sink, shower/bathtub) on an upscaled image
       direct  the VLM answers the count directly (no evidence; used only where it beats the rest)
       prior   most common TRAIN answer for the class (never refuse: D4)
  3. evidence = one point per counted object (image_px); confidence = TRAIN hit rate of the chosen method;
     the prior answer and its hit rate are always in the trace as a cross-check.

Options (`--solver-arg k=v`):
  gate      override, e.g. "window:points,door:direct" (others from gate.json)
  backend   local (default) | nvidia
  target_px upscale small images to about this many pixels before pointing (default 2,000,000)
"""

from __future__ import annotations

import collections
import json
import threading
from pathlib import Path

from stoa.contract import Answer, Evidence
from stoa.data import source_of
from stoa.solvers import register
from stoa.solvers.base import BaseSolver
from stoa.solvers.raster import vlm
from stoa.solvers.raster.classes import ROOM_CLASSES, SYMBOL_CLASSES, question_class, question_op, type_code

CANONICAL = {  # used when a composition needs a `direct` answer for one part
    "window": "How many windows are shown on this floor plan?",
    "door": "How many doors are shown on this floor plan? Count doorways fitted with a door; open doorways "
            "without a door leaf do not count.",
    "storey": "How many floors (storeys) does this floor plan show?",
    "wc_seat": "How many toilet bowls (WC seats) are drawn on this floor plan?",
    "sink": "How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts as one) are "
            "drawn on this floor plan?",
    "shower_bath": "How many showers and bathtubs are drawn on this floor plan in total?",
}
IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
GATE_FILE = Path(__file__).with_name("gate.json")
COND_FILE = Path(__file__).with_name("cond_prior.json")  # experiments/w3/cv/cond_prior.py --write

# Before calibration: R1's HYBRID label policy (chosen on 60 TRAIN drawings, +13.5 pts on dev, KNOWLEDGE 23:57),
# prior for the rest. Methods: prior | labels | max1 (= max(1, labels)) | labels_code (labels, else the apartment
# type code such as "3H+K+S") | rooms_rule (sinks from room labels) | cond_prior (count given room counts) |
# points | direct. Sauna labels_code: 69% vs labels 62% on TRAIN (label_policy.py).
DEFAULT_GATE = {"bedroom": "labels", "kitchen": "prior", "bathroom": "max1", "wc_room": "labels",
                "sauna": "labels_code", "balcony": "labels",
                **{c: "prior" for c in SYMBOL_CLASSES}, "storey": "prior"}


def load_gate() -> dict:
    """{class: {"method": str, "acc": {method: train accuracy}}} or the default gate."""
    if GATE_FILE.exists():
        return json.loads(GATE_FILE.read_text())
    return {c: {"method": m, "acc": {}} for c, m in DEFAULT_GATE.items()}


_prior_lock = threading.Lock()
_PRIOR: dict | None = None


def class_prior() -> dict:
    """{class: (mode answer, hit rate, n)} from the TRAIN split, cubicasa only (EN+FI pooled)."""
    global _PRIOR
    with _prior_lock:
        if _PRIOR is None:
            from stoa.eval.splits import load_split

            by = collections.defaultdict(list)
            for q in load_split("train"):
                if q.source != "cubicasa5k" or q.type != "count":
                    continue
                c = question_class(q.question)
                if c:
                    by[c].append(q.answer)
            _PRIOR = {}
            for c, vals in by.items():
                v, n = collections.Counter(vals).most_common(1)[0]
                _PRIOR[c] = (v, n / len(vals), len(vals))
        return _PRIOR


@register("raster")
class RasterSolver(BaseSolver):
    extensions = IMG_EXT

    def __init__(self, gate: str = "", backend: str = "local", target_px: int | str = 2_000_000, **kwargs):
        super().__init__(**kwargs)
        self.backend = backend
        self.target_px = int(target_px)
        self.gate = load_gate()
        for part in filter(None, (gate or "").split(",")):
            c, m = part.split(":")
            self.gate.setdefault(c, {"acc": {}})["method"] = m

    def can_handle(self, path: str, question: str) -> bool:
        return self._raster_file(path) is not None and question_op(question)[0] != "none"

    # ----------------------------------------------------------------------------------------------
    def solve(self, path: str, question: str) -> Answer:
        op, classes = question_op(question)
        if op in ("single", "none"):
            return self._solve_class(path, question, classes[0] if classes else None)
        # compositions over our classes: sum ("doors and windows in total"), diff ("how many more X than Y"),
        # exists ("does it have a sauna? yes/no"). Each part is answered by its own gated method.
        parts = [self._solve_class(path, None, c) for c in classes]
        trace = [f"composition op={op} over {classes}"]
        for c, a in zip(classes, parts):
            trace.append(f"[{c}] = {a.value} (conf {a.confidence:.2f})")
            trace.extend(f"  [{c}] {t}" for t in a.trace)
        ev = [e for a in parts for e in a.evidence]
        assumptions = [x for a in parts for x in a.assumptions]
        missing = [x for a in parts for x in a.missing]
        conf = 1.0
        for a in parts:
            conf *= a.confidence
        if any(a.value is None for a in parts):
            return Answer(value=None, unit="count", solver=self.name, trace=trace, missing=missing or ["part"])
        vals = [int(a.value) for a in parts]
        if op == "sum":
            value, unit = sum(vals), "count"
        elif op == "diff":
            value, unit = vals[0] - vals[1], "count"
        else:
            value, unit = ("yes" if vals[0] > 0 else "no"), None
        trace.append(f"answer = {op}({vals}) = {value}")
        return Answer(value=value, unit=unit, confidence=round(conf, 3), evidence=ev, solver=self.name,
                      trace=trace, assumptions=assumptions, missing=missing)

    def _solve_class(self, path: str, question: str | None, cls: str | None) -> Answer:
        """One object class. `question` is only needed by the `direct` method (None inside compositions:
        a canonical English question for the class is used)."""
        question = question or CANONICAL.get(cls, "")
        trace = [f"class={cls}"]
        prior = class_prior().get(cls) if cls else None
        if prior:
            trace.append(f"prior (train mode for {cls}) = {prior[0]} (hit rate {prior[1]:.0%}, n={prior[2]})")
        if cls is None:
            return Answer(value=None, unit="count", solver=self.name, trace=trace + ["unknown object class"],
                          missing=["question not recognised as a count of a known object class"])
        g = self.gate.get(cls, {"method": "prior", "acc": {}})
        method = g["method"]
        acc = g.get("acc", {})
        trace.append(f"gate[{cls}] = {method} (train acc {acc})")
        if method == "prior":
            return self._prior_answer(cls, prior, trace, acc)
        src = self._raster_file(path)
        if src is None:  # not an image and no PNG/JPG sibling: let the cascade move on (W4 pipeline)
            ans = self._prior_answer(cls, prior, trace + ["no raster version of this drawing"], acc)
            ans.value = None
            ans.missing.append("no raster image of this drawing")
            return ans
        if src != path:
            trace.append(f"using raster sibling {src}")
        img = vlm.llm.load_image(self.abspath(src))
        key = src
        path = src  # evidence boxes are in this image's pixels
        try:
            if method in ("labels", "max1", "labels_code"):
                return self._labels(path, img, key, cls, prior, trace, acc, method)
            if method == "rooms_rule":
                return self._rooms_rule(path, img, key, cls, prior, trace, acc)
            if method == "cond_prior":
                return self._cond_prior(path, img, key, cls, prior, trace, acc)
            if method == "points":
                return self._points(path, img, key, cls, prior, trace, acc)
            if method == "direct":
                v, log = vlm.direct_count(img, question, self.backend)
                trace.append(f"direct: raw={log.raw!r} {log.seconds:.1f}s")
                if v is not None:
                    return Answer(value=v, unit="count", confidence=acc.get("direct", 0.3), solver=self.name,
                                  trace=trace, assumptions=["direct VLM count; no per-object evidence"],
                                  missing=["per-object locations (direct count has no evidence)"])
        except Exception as e:  # noqa: BLE001 - never refuse: fall back to the prior
            trace.append(f"{method} failed: {type(e).__name__}: {str(e)[:150]}")
        return self._prior_answer(cls, prior, trace, acc)

    def _raster_file(self, path: str) -> str | None:
        """The image to read: the path itself, or a PNG/JPG sibling of a PDF/other format (same drawing)."""
        if Path(path).suffix.lower() in IMG_EXT:
            return path
        sib = self.siblings(path)
        return next((sib[e] for e in (".png", ".jpg", ".jpeg") if e in sib), None)

    def _prior_answer(self, cls, prior, trace, acc) -> Answer:
        if not prior:
            return Answer(value=None, unit="count", solver=self.name, trace=trace + ["no prior"],
                          missing=["no prior for this class"])
        return Answer(value=prior[0], unit="count", confidence=round(prior[1], 3), solver=self.name,
                      trace=trace + ["answer = prior"],
                      assumptions=[f"typical Finnish apartment plan: {prior[0]} {cls.replace('_', ' ')} "
                                   f"({prior[1]:.0%} of training plans)"],
                      missing=[f"a reliable detection of each {cls.replace('_', ' ')} on this drawing"])

    def _labels(self, path, img, key, cls, prior, trace, acc, method="labels") -> Answer:
        items, log, hit = vlm.read_labels(img, key, self.backend)
        trace.append(f"labels{' (shared with another question)' if hit else ''}: {len(items)} read in "
                     f"{log.seconds:.1f}s: " + ", ".join(f"{i.text}->{i.cls or '-'}" for i in items)[:600])
        trace.extend(log.notes)
        name = cls.replace("_", " ")
        if any(n.startswith("LOOP") for n in log.notes):
            ans = self._prior_answer(cls, prior, trace, acc)
            ans.missing.append("the label reading degenerated (repetition loop); answered with the prior")
            return ans
        hits = [i for i in items if i.cls == cls]
        ev = [Evidence(file=path, bbox=[round(v, 1) for v in getattr(i, "box", [i.x, i.y, i.x, i.y])],
                       bbox_space="image_px", note=f"label '{i.text}' = {name} {k + 1}") for k, i in enumerate(hits)]
        value = len(hits)
        codes = [(i, type_code(i.text)) for i in items if type_code(i.text)]
        if codes:
            ci, tc = codes[0]
            if cls == "bedroom":
                implied = max(0, tc["rooms"] - 1) if tc["rooms"] else 0
            else:
                implied = int(cls in tc["classes"])
            trace.append(f"apartment type code '{ci.text}' implies {cls}={implied}")
            if method == "labels_code" and value == 0 and implied:
                value = implied
                ev = [Evidence(file=path, bbox=[round(v, 1) for v in getattr(ci, "box", [ci.x, ci.y, ci.x, ci.y])],
                               bbox_space="image_px", note=f"apartment type '{ci.text}' -> {name} {implied}")]
                trace.append("no room label found; answer taken from the apartment type code")
        assumptions = [f"counted room-name labels for {name} (Finnish codes: MH bedroom, KH/PH/PESUH bathroom, "
                       f"S/SAUNA/LH sauna, WC, PARV balcony, K/KK/KT kitchen); one label = one room"]
        if method == "max1" and value == 0:
            value = 1
            assumptions.append(f"no {name} label read, but nearly every plan has one: assumed 1")
        if prior:
            trace.append(f"cross-check vs prior {prior[0]}: {'agrees ✓' if prior[0] == value else 'differs'}")
        return Answer(value=value, unit="count", confidence=acc.get(method, 0.5), evidence=ev, solver=self.name,
                      trace=trace, assumptions=assumptions,
                      missing=([] if hits else [f"no {name} label found; an unlabelled room would be missed"]))

    def _rooms_rule(self, path, img, key, cls, prior, trace, acc) -> Answer:
        """Fixtures implied by rooms (same label call as the room questions, no extra cost). Only `sink` so far:
        sinks = 1 kitchen sink + max(1, #bathroom labels) basins + #WC-room labels basins.
        TRAIN (200 drawings, experiments/w3/cv/fixture_rules.py): 70.4% vs prior 56.3%."""
        if cls != "sink":
            return self._prior_answer(cls, prior, trace + [f"no room rule for {cls}"], acc)
        items, log, hit = vlm.read_labels(img, key, self.backend)
        trace.append(f"labels{' (shared with another question)' if hit else ''}: {len(items)} read in "
                     f"{log.seconds:.1f}s: " + ", ".join(f"{i.text}->{i.cls or '-'}" for i in items)[:600])
        trace.extend(log.notes)
        if any(n.startswith("LOOP") for n in log.notes):
            ans = self._prior_answer(cls, prior, trace, acc)
            ans.missing.append("the label reading degenerated (repetition loop); answered with the prior")
            return ans
        by = collections.defaultdict(list)
        for i in items:
            if i.cls in ("kitchen", "bathroom", "wc_room"):
                by[i.cls].append(i)
        n_bath, n_wc = max(1, len(by["bathroom"])), len(by["wc_room"])
        value = 1 + n_bath + n_wc
        trace.append(f"rule: sinks = 1 (kitchen) + max(1, {len(by['bathroom'])} bathroom labels) + {n_wc} WC labels "
                     f"= {value}")

        def ev(i, note):
            return Evidence(file=path, bbox=[round(v, 1) for v in getattr(i, "box", [i.x, i.y, i.x, i.y])],
                            bbox_space="image_px", note=note)
        evidence = [ev(by["kitchen"][0], f"kitchen '{by['kitchen'][0].text}' -> kitchen sink")] if by["kitchen"] else []
        evidence += [ev(i, f"bathroom '{i.text}' -> wash basin") for i in by["bathroom"]]
        evidence += [ev(i, f"WC '{i.text}' -> wash basin") for i in by["wc_room"]]
        assumptions = ["sinks inferred from rooms: one kitchen sink, one wash basin per bathroom (at least one) and "
                       "one per WC room; double-bowl sinks count once"]
        if not by["kitchen"]:
            assumptions.append("no kitchen label read; assumed the plan has one kitchen")
        if not by["bathroom"]:
            assumptions.append("no bathroom label read; assumed one bathroom")
        if prior:
            trace.append(f"cross-check vs prior {prior[0]}: {'agrees ✓' if prior[0] == value else 'differs'}")
        return Answer(value=value, unit="count", confidence=acc.get("rooms_rule", 0.6), evidence=evidence,
                      solver=self.name, trace=trace, assumptions=assumptions,
                      missing=["sink symbols are not detected individually; extra basins (utility room, double "
                               "basins) would be missed"])

    def _cond_prior(self, path, img, key, cls, prior, trace, acc) -> Answer:
        """Best estimate when the symbols themselves cannot be counted reliably (doors, windows, WC seats): the most
        common TRAIN count among plans with the same room counts read from the labels (e.g. 2 bedrooms, 1 WC,
        a sauna -> 8 doors). Uses the label call shared with the room questions (no extra model call).
        TRAIN, 2-fold held-out gain vs the prior: doors +5.8, windows +6.6, WC seats +7.9 (cond_prior.py)."""
        spec = json.loads(COND_FILE.read_text()).get(cls) if COND_FILE.exists() else None
        if not spec:
            return self._prior_answer(cls, prior, trace + [f"no conditional table for {cls}"], acc)
        items, log, hit = vlm.read_labels(img, key, self.backend)
        trace.append(f"labels{' (shared with another question)' if hit else ''}: {len(items)} read in "
                     f"{log.seconds:.1f}s: " + ", ".join(f"{i.text}->{i.cls or '-'}" for i in items)[:600])
        trace.extend(log.notes)
        if any(n.startswith("LOOP") for n in log.notes):
            ans = self._prior_answer(cls, prior, trace, acc)
            ans.missing.append("the label reading degenerated (repetition loop); answered with the prior")
            return ans
        n = collections.Counter(i.cls for i in items if i.cls)
        codes = [type_code(i.text) for i in items if type_code(i.text)]
        feats = {"bedroom": n["bedroom"], "wc_room": n["wc_room"], "balcony": n["balcony"],
                 "bathroom": max(1, n["bathroom"]),
                 "sauna": n["sauna"] or int(bool(codes and "sauna" in codes[0]["classes"]))}
        fx = [feats[f] for f in spec["features"]]
        cell = spec["table"].get(",".join(str(int(v)) for v in fx))
        desc = ", ".join(f"{v} {f.replace('_', ' ')}" for f, v in zip(spec["features"], fx))
        name = cls.replace("_", " ")
        if not cell:
            ans = self._prior_answer(cls, prior, trace + [f"rooms read: {desc}; too few training plans like this"], acc)
            return ans
        value = int(cell["mode"]) if float(cell["mode"]).is_integer() else cell["mode"]
        trace.append(f"rooms read: {desc} -> among {cell['n']} training plans with these rooms the most common "
                     f"{name} count is {value} ({cell['hit']:.0%} of them)")
        if prior:
            trace.append(f"cross-check vs plain prior {prior[0]}: {'agrees ✓' if prior[0] == value else 'differs'}")
        basis = [i for i in items if i.cls in spec["features"]]
        ev = [Evidence(file=path, bbox=[round(v, 1) for v in getattr(i, "box", [i.x, i.y, i.x, i.y])],
                       bbox_space="image_px", note=f"basis of the estimate: {i.cls.replace('_', ' ')} label '{i.text}'")
              for i in basis]
        conf = round(max(0.05, min(0.9, 0.8 * cell["hit"])), 3)  # read labels are noisier than gold (train: x0.8)
        return Answer(value=value, unit="count", confidence=conf, evidence=ev, solver=self.name, trace=trace,
                      assumptions=[f"statistical estimate: plans with {desc} most often have {value} {name}s "
                                   f"(training data, {cell['n']} plans); the {name} symbols were not counted one by one"],
                      missing=[f"a reliable detection of each {name} symbol (8B VLM pointing and classical CV both "
                               f"failed on TRAIN)"])

    def _points(self, path, img, key, cls, prior, trace, acc) -> Answer:
        items, log, hit = vlm.point_symbols(img, key, cls, self.backend, self.target_px)
        trace.append(f"points{' (cached)' if hit else ''}: {len(items)} in {log.seconds:.1f}s")
        trace.extend(log.notes)
        ev = [Evidence(file=path, bbox=[i.x, i.y, i.x, i.y], bbox_space="image_px",
                       note=f"{i.text} {k + 1}") for k, i in enumerate(items)]
        return Answer(value=len(items), unit="count", confidence=acc.get("points", 0.3), evidence=ev,
                      solver=self.name, trace=trace,
                      assumptions=[f"each {vlm.SYMBOL_DEF[cls][0]} symbol pointed at once by the VLM"],
                      missing=["symbol detections are not verified individually"])
