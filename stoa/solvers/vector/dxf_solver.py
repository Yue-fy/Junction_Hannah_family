"""`dxf` solver: swiss_dwellings questions answered from the sibling DXF, evidence on the asked file.

Pipeline (deterministic, no model, ~10-50 ms per question after the first load of a floor):
  question --qparse--> Query(terms, op) --FloorModel--> value per term --op--> answer
  evidence: one box per counted object / room polygon, DXF metres -> PDF points (text-anchored fit) -> PNG px.
Cross-check (linked data): a room's DXF polygon area vs. the "16.78 m²" printed in that room on the plan.
"""

from __future__ import annotations

import re
from pathlib import Path

from stoa.contract import Answer, Evidence
from stoa.data import abspath, siblings, source_of
from stoa.solvers import register
from stoa.solvers.base import BaseSolver
from stoa.solvers.vector import qparse
from stoa.solvers.vector.floor import FloorModel, Room, load_floor, window_count
from stoa.solvers.vector.pdfmap import fit_transform, pdf_span_counts, png_scale

M2_TO_FT2 = 10.763910416709722

# every room name seen in the swiss DXFs (so a label absent from this floor still parses -> count 0)
KNOWN_NAMES = [
    "Zimmer", "Bad", "Korridor", "Küche", "Balkon", "Pièce", "Wohnen/Essen", "Bain", "Couloir", "Schlafzimmer",
    "Cuisine", "Balcon", "Stanza", "Reduit", "Treppenhaus", "Wohnen", "Bagno", "Lift", "Corridoio", "Séjour/repas",
    "Chambre à coucher", "Cucina", "Loggia", "Réduit", "Cage d'escalier", "Ripostiglio", "Séjour", "Camera da letto",
    "Balcone", "Soggiorno/pranzo", "Essen", "Vano scala", "Ascenseur", "Raum", "Terrasse", "Soggiorno", "Ascensore",
    "Repas", "Compartiment cave", "Pranzo", "Wintergarten",
]

# measured exact-match / within-2% rates of each rule (train floors, see stoa/solvers/vector/README.md);
# used as the answer's confidence
RULE_CONF = {
    "count:door": 0.99, "count:window": 0.99, "count:apartment": 0.99, "count:bathtub": 0.99, "count:shower": 0.99,
    "count:toilet": 0.95, "count:washbasin": 0.95, "count_label": 0.98, "area_room": 0.98, "area_label": 0.98,
    "area_apartment": 0.93, "area_total": 0.90,
}

KIND_DESC = {
    "door": "door leaves (5-vertex polylines) on DXF layer DOOR",
    "window": "windows on DXF layer WINDOW (3 polylines per window)",
    "toilet": "toilet bowls: 48-vertex ellipses on DXF layer FIXTURE without a drain circle",
    "washbasin": "washbasins: 48-vertex ellipses on DXF layer FIXTURE with a drain circle",
    "bathtub": "bathtubs: 69-vertex outlines on DXF layer FIXTURE",
    "shower": "shower trays: 5-vertex outlines on DXF layer FIXTURE",
    "apartment": "apartment labels ('Whg. X' / 'App. X') on DXF layer ROOM_TEXT",
}


class _Part:
    """Result of one term: value + DXF-space evidence + trace/assumptions."""

    def __init__(self, value, conf, boxes, trace, assumptions=None, missing=None, extra_notes=None):
        self.value = value
        self.conf = conf
        self.boxes = boxes  # list of (dxf_bbox, note)
        self.trace = trace
        self.assumptions = assumptions or []
        self.missing = missing or []
        self.extra_notes = extra_notes or []


def _room_note(r: Room) -> str:
    note = f"room {r.label()}: {r.area:.2f} m²"
    if r.printed_area is not None:
        ok = abs(r.printed_area - r.area) <= 0.02 * max(r.printed_area, 1e-9)
        note += f" (plan prints {r.printed_area:.2f} m² {'✓' if ok else '✗'})"
    return note


def _rooms_with_name(fm: FloorModel, name) -> list[Room]:
    names = name if isinstance(name, list) else [name]
    exact = [r for r in fm.rooms if r.name in names]
    if exact:
        return exact
    low = {n.lower() for n in names}
    return [r for r in fm.rooms if (r.name or "").lower() in low]


def _eval_term(fm: FloorModel, t: qparse.Term, qtype: str) -> _Part:
    k = t.kind
    if k == "count":
        kind = t.arg
        if kind == "apartment":
            boxes = [((u.text.bbox if u.text else u.bbox), f"apartment {u.label}") for u in fm.units]
            return _Part(len(fm.units), RULE_CONF["count:apartment"], boxes,
                         [f"apartments = {len(fm.units)} labels {sorted(u.label for u in fm.units)}"],
                         [f"counted {KIND_DESC['apartment']}"])
        items = fm.items.get(kind, [])
        n = window_count(fm) if kind == "window" else len(items)
        tr = [f"{kind}s = {n} ({KIND_DESC[kind]})"]
        if kind == "window" and n != len(items):
            tr.append(f"window boxes grouped into {len(items)} clusters; count uses polylines/3")
        return _Part(n, RULE_CONF[f"count:{kind}"], [(it.bbox, it.note) for it in items], tr, [f"counted {KIND_DESC[kind]}"])
    if k == "count_label":
        if t.arg == "<numbered>":
            rooms = [r for r in fm.rooms if r.number]
            return _Part(len(rooms), 0.5, [(r.bbox, _room_note(r)) for r in rooms],
                         [f"rooms with a number = {len(rooms)}"], ["'rooms' read as every numbered room polygon"])
        names = t.arg if isinstance(t.arg, list) else [t.arg]
        texts = [tx for tx in fm.texts if tx.text in names] or [tx for tx in fm.texts if tx.text.lower() in {n.lower() for n in names}]
        boxes = []
        for tx in texts:
            room = next((r for r in fm.rooms if tx in r.texts), None)
            boxes.append((room.bbox if room else tx.bbox, f"'{tx.text}'" + (f" room {room.number}" if room and room.number else "")))
        conf = RULE_CONF["count_label"] * (0.7 if t.note.startswith("concept") else 1.0)
        asm = [f"{t.note}: labels {names}"] if t.note else []
        return _Part(len(texts), conf, boxes, [f"rooms labelled {names} = {len(texts)} ROOM_TEXT entries"], asm)
    if k == "area_room":
        rooms = [r for r in fm.rooms if r.number == t.arg]
        if not rooms:
            return _Part(None, 0.0, [], [f"room {t.arg} not found"], missing=[f"room number {t.arg} not on this floor"])
        r = rooms[0]
        val, notes = r.area, []
        if r.printed_area is not None and abs(r.printed_area - r.area) > 0.02 * r.printed_area:
            notes.append(f"DXF polygon {r.area:.2f} m² disagrees with printed {r.printed_area:.2f} m²; used printed")
            val = r.printed_area
        conf = RULE_CONF["area_room"] if r.printed_area is None else 0.995
        return _Part(val, conf, [(r.bbox, _room_note(r))], [f"room {r.label()} polygon area {r.area:.3f} m²", *notes],
                     ["net floor area = area of the room's ROOM_OUTLINE polygon in the DXF (metres)"])
    if k == "area_label":
        rooms = _rooms_with_name(fm, t.arg)
        val = sum(r.area for r in rooms)
        names = t.arg if isinstance(t.arg, list) else [t.arg]
        asm = ["net floor area = sum of ROOM_OUTLINE polygon areas"] + ([f"{t.note}: labels {names}"] if t.note else [])
        conf = RULE_CONF["area_label"] * (0.7 if t.note.startswith("concept") else 1.0)
        return _Part(val, conf, [(r.bbox, _room_note(r)) for r in rooms],
                     [f"{len(rooms)} rooms labelled {names}: " + " + ".join(f"{r.area:.2f}" for r in rooms)], asm)
    if k == "area_apartment":
        unit = next((u for u in fm.units if u.label == t.arg), None)
        if unit is None:
            return _Part(None, 0.0, [], [f"apartment {t.arg} not found; labels {[u.label for u in fm.units]}"],
                         missing=[f"no 'Whg./App. {t.arg}' label on this floor"])
        rooms = [r for r in fm.rooms if r.unit == t.arg and r.number and not r.outdoor]
        excl = [r for r in fm.rooms if r.unit == t.arg and (r.outdoor or not r.number)]
        val = sum(r.area for r in rooms)
        tr = [f"apartment {t.arg}: {len(rooms)} numbered indoor rooms inside its UNIT_OUTLINE = {val:.2f} m²"]
        if excl:
            tr.append("excluded: " + ", ".join(r.label() for r in excl))
        asm = ["apartment = rooms whose label lies inside the UNIT_OUTLINE holding 'Whg./App. X'",
               "outdoor rooms (Balkon/Loggia/Terrasse/…) excluded"]
        conf, asm2, miss = _unnamed_caveat(rooms, val)
        return _Part(val, min(conf, RULE_CONF["area_apartment"]) if unit.poly is not None else 0.3,
                     [(r.bbox, _room_note(r)) for r in rooms], tr, asm + asm2, miss)
    if k == "area_total":
        rooms = [r for r in fm.rooms if r.number and not r.outdoor and not r.shaft]
        excl = [r for r in fm.rooms if r.number and (r.outdoor or r.shaft)]
        val = sum(r.area for r in rooms)
        tr = [f"{len(rooms)} numbered indoor rooms = {val:.2f} m²"]
        if excl:
            tr.append("excluded outdoor/shaft: " + ", ".join(r.label() for r in excl))
        asm = ["total = numbered ROOM_OUTLINE polygons, minus outdoor rooms (Balkon/Loggia/Terrasse/…) and shafts"]
        if t.note:
            asm.append(t.note)
        conf, asm2, miss = _unnamed_caveat(rooms, val)
        return _Part(val, min(conf, RULE_CONF["area_total"] + 0.06), [(r.bbox, _room_note(r)) for r in rooms], tr,
                     asm + asm2, miss)
    return _Part(None, 0.0, [], [f"unknown term {k}"])


def _unnamed_caveat(rooms: list[Room], total: float):
    """Numbered rooms without a name are the only source of error in apartment/floor totals (train: every
    overshoot is explained by 1-3 such rooms or a misassigned room; geometry can't tell which ones the
    reference drops). Keep them, but say so and lower the confidence."""
    un = [r for r in rooms if not r.name]
    if not un:
        return 0.97, [], []
    a = sum(r.area for r in un)
    lo = total - a
    share = a / total if total else 0
    conf = 0.95 if share < 0.02 else 0.8
    return conf, [f"included {len(un)} numbered rooms without a name ({a:.2f} m²: "
                  + ", ".join(r.number for r in un[:8]) + "); without them the total is "
                  + f"{lo:.2f} m²"], ["room type of unnamed numbered rooms (shaft/void or storage?)"]


class _Mapper:
    """DXF bbox -> Evidence on the asked file (PDF points or PNG pixels); falls back to the PDF sibling."""

    def __init__(self, path: str, dxf_rel: str):
        self.path = path
        sib = siblings(path)
        ext = Path(path).suffix.lower()
        self.pdf_rel = path if ext == ".pdf" else sib.get(".pdf")
        self.tf = None
        self.file, self.space, self.k = None, None, 1.0
        if self.pdf_rel:
            self.tf = fit_transform(str(abspath(self.pdf_rel)), str(abspath(dxf_rel)))
        if self.tf is not None:
            if ext == ".png":
                self.file, self.space = path, "image_px"
                self.k = png_scale(str(abspath(path)), self.tf.page_w)
            else:
                self.file, self.space = self.pdf_rel, "pdf_pt"
        self.dxf_rel = dxf_rel

    def ev(self, bb, note) -> Evidence:
        if self.tf is None:
            return Evidence(file=self.dxf_rel, note=f"{note} [DXF m: {bb[0]:.2f},{bb[1]:.2f},{bb[2]:.2f},{bb[3]:.2f}]")
        b = self.tf.box(bb, pad_pt=1.0)
        b = [round(v * self.k, 1) for v in b]
        return Evidence(file=self.file, page=0 if self.space == "pdf_pt" else None, bbox=b, bbox_space=self.space,
                        note=note)


@register("dxf")
class DxfSolver(BaseSolver):
    """Options: llm=1 (table-QA fallback for questions the rule parser doesn't cover), backend=local|nvidia."""

    sources = ("swiss_dwellings",)

    def __init__(self, llm: int | str = 1, backend: str = "local", **kwargs):
        super().__init__(**kwargs)
        self.llm = bool(int(llm))
        self.backend = backend

    def can_handle(self, path: str, question: str) -> bool:
        if source_of(path) != "swiss_dwellings" and Path(path).suffix.lower() != ".dxf":
            return False
        return Path(path).suffix.lower() == ".dxf" or abspath(str(Path(path).with_suffix(".dxf"))).exists()

    def solve(self, path: str, question: str) -> Answer:
        dxf_rel = path if path.lower().endswith(".dxf") else siblings(path).get(".dxf")
        if not dxf_rel:
            return self.abstain("no DXF sibling")
        fm = load_floor(str(abspath(dxf_rel)))
        vocab = fm.names() + KNOWN_NAMES
        qr = qparse.parse(question, vocab, room_numbers={r.number for r in fm.rooms if r.number})
        trace = [f"parsed: {qr.describe()}", *[f"parse note: {n}" for n in qr.notes]]
        if self.llm and not qparse.covered(question, qr):
            ans = self._tableqa(path, dxf_rel, fm, question, trace)
            if ans is not None:
                return ans
        if not qr.terms:
            return Answer.abstain(self.name, "question not understood by the DXF parser", trace)
        parts = [_eval_term(fm, t, qr.qtype) for t in qr.terms]
        for t, p in zip(qr.terms, parts):
            trace += p.trace
        assumptions = [a for p in parts for a in p.assumptions]
        missing = [m for p in parts for m in p.missing]
        vals = [p.value for p in parts]
        known = [v for v in vals if v is not None]
        if not known:
            return Answer(value=None, unit=qr.unit, confidence=0.0, solver=self.name, trace=trace + ["abstain: no term resolved"],
                          missing=missing or ["nothing matched on this floor"])
        conf = 1.0
        for p in parts:
            conf *= p.conf if p.value is not None else 0.2
        # combine --------------------------------------------------------------------------------
        value: float | int | str
        unit = qr.unit
        if qr.qtype == "text" and qr.op in ("max", "min"):
            pairs = [(v, t) for v, t in zip(vals, qr.terms) if v is not None]
            v, t = (max if qr.op == "max" else min)(pairs, key=lambda vt: vt[0])
            value = str(t.arg if not isinstance(t.arg, list) else t.arg[0])
            trace.append(f"{qr.op} -> {value} ({v:.2f} m²)")
            unit = None
        elif qr.op == "diff":
            value = known[0] - sum(known[1:])
            trace.append(f"difference: {' - '.join(str(round(v, 2)) for v in known)} = {value:.2f}")
        else:
            value = sum(known)
            if len(known) > 1:
                trace.append(f"sum: {' + '.join(str(round(v, 2)) for v in known)} = {value:.2f}")
        if unit == "count":
            value = int(round(value))
        elif unit == "ft2":
            value = round(value * M2_TO_FT2, 2)
            assumptions.append("converted m² -> ft² (1 m² = 10.7639 ft²)")
        elif unit == "m2":
            value = round(value, 2)
        # linked data: the PDF text layer is an independent rendering of the same drawing -> cross-check
        mapper = _Mapper(path, dxf_rel)
        if mapper.pdf_rel:
            conf = self._cross_check(mapper.pdf_rel, fm, qr, parts, trace, conf)
        # evidence -------------------------------------------------------------------------------
        evidence = [mapper.ev(bb, note) for p in parts for bb, note in p.boxes]
        if mapper.tf is not None:
            trace.append(f"DXF->PDF fit on {mapper.tf.n_anchors} text anchors, rms {mapper.tf.rms_pt:.2f} pt, "
                         f"scale 1:{mapper.tf.scale_ratio:.0f}")
        else:
            missing.append("could not map DXF to the PDF page (no matching text); evidence in DXF metres")
        if fm.warnings:
            trace += [f"warning: {w}" for w in fm.warnings[:3]]
        return Answer(value=value, unit=unit, confidence=round(min(max(conf, 0.0), 1.0), 3), evidence=evidence,
                      trace=trace, solver=self.name, assumptions=list(dict.fromkeys(assumptions)), missing=missing)

    @staticmethod
    def _cross_check(pdf_rel: str, fm: FloorModel, qr, parts, trace: list[str], conf: float) -> float:
        try:
            spans = pdf_span_counts(str(abspath(pdf_rel)))
        except Exception:  # noqa: BLE001
            return conf
        for t, p in zip(qr.terms, parts):
            if p.value is None:
                continue
            if t.kind == "count_label" and t.arg != "<numbered>":
                names = t.arg if isinstance(t.arg, list) else [t.arg]
                n_pdf = sum(spans.get(nm, 0) for nm in names)
                ok = n_pdf == p.value
                trace.append(f"cross-check: PDF text layer shows {n_pdf} label(s) {names} {'✓' if ok else '✗'} (DXF {p.value})")
                conf = conf if ok else conf * 0.7
            elif t.kind == "count" and t.arg == "apartment":
                n_pdf = sum(v for k, v in spans.items() if re.match(r"^(Whg|App)\.\s*[A-Z0-9]{1,3}$", k))
                ok = n_pdf == p.value
                trace.append(f"cross-check: PDF text layer shows {n_pdf} apartment labels {'✓' if ok else '✗'} (DXF {p.value})")
                conf = conf if ok else conf * 0.7
            elif t.kind == "area_room":
                r = next((r for r in fm.rooms if r.number == t.arg), None)
                if r is not None and r.printed_area is not None:
                    trace.append(f"cross-check: plan prints {r.printed_area:.2f} m² for room {r.number} "
                                 f"({'✓' if abs(r.printed_area - r.area) <= 0.02 * r.printed_area else '✗'} DXF polygon {r.area:.2f} m²)")
        return conf

    def _tableqa(self, path: str, dxf_rel: str, fm: FloorModel, question: str, trace: list[str]) -> Answer | None:
        """LLM writes pandas over the floor's rooms/objects/apartments tables; we run it (stoa.solvers.vector.tableqa)."""
        from stoa.solvers.vector import tableqa

        trace = [*trace, "rule parser does not cover this question -> table QA over the DXF floor tables"]
        try:
            tables = tableqa.floor_tables(fm)
            res = tableqa.ask(question, tables, backend=self.backend)
        except Exception as e:  # noqa: BLE001 - LLM down etc.: fall back to the rules
            trace.append(f"table QA failed: {type(e).__name__}: {e}")
            return None
        if res.get("value") is None:
            trace.append(f"table QA gave no answer ({res.get('error')})")
            return None
        trace += ["table QA code: " + " ; ".join(ln.strip() for ln in res["code"].splitlines() if ln.strip())[:600]]
        mapper = _Mapper(path, dxf_rel)
        by_id = {r.idx: r for r in fm.rooms}
        evidence = [mapper.ev(by_id[i].bbox, _room_note(by_id[i])) for i in res["used"] if i in by_id]
        value, unit = res["value"], res.get("unit")
        yesno = bool(qparse.YESNO.match(question.strip()))
        if isinstance(value, bool) or (yesno and isinstance(value, (int, float))):
            trace.append(f"yes/no question; query returned {value!r}")
            value, unit = ("yes" if value else "no"), None
        if isinstance(value, str):
            unit = None
        if unit == "count" and isinstance(value, (int, float)):
            value = int(round(value))
        elif isinstance(value, float):
            value = round(value, 2)
        if unit not in ("count", "m2", None):
            unit = None
        return Answer(value=value, unit=unit, confidence=0.6 if evidence else 0.45, evidence=evidence, trace=trace,
                      solver=self.name, assumptions=["the model wrote the query; every number comes from the DXF tables"],
                      missing=[] if evidence else ["the query did not report which rooms it used"])
