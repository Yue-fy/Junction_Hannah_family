"""`dxf` solver: swiss_dwellings questions answered from the sibling DXF, evidence on the asked file.

Pipeline (deterministic, no model, ~10-50 ms per question after the first load of a floor):
  question --qparse--> Query(terms, op) --FloorModel--> value per term --op--> answer
  evidence: one box per counted object / room polygon, DXF metres -> PDF points (text-anchored fit) -> PNG px.
Cross-check (linked data): a room's DXF polygon area vs. the "16.78 m²" printed in that room on the plan.
"""

from __future__ import annotations

import os
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


OPCHECK_KINDS = {
    "A": "one value, or the total/sum of the named things", "B": "difference between two things",
    "C": "ratio / how many times", "D": "percentage or share of a whole", "E": "average",
    "F": "how many items are above/below a threshold", "G": "a total excluding some part (e.g. not in apartment X)",
    "H": "which of the named things is larger/smaller (a name)", "I": "largest/smallest of a set", "J": "yes/no",
    "K": "something else",
}
OPCHECK_PROMPT = ("Classify the operation this floor-plan question asks for. Reply with ONE capital letter only.\n"
                  + "\n".join(f"{k}: {v}" for k, v in OPCHECK_KINDS.items()) + "\nQuestion: {q}\nLetter:")


def _rewrite_by_op(qr: qparse.Query, letter: str | None) -> qparse.Query | None:
    """Apply the operation the LLM named to the apartment parts the rules found (None if they do not fit)."""
    apts = [t for t in qr.terms if t.kind == "area_apartment"]
    if qr.qtype != "area" or len(apts) != len(qr.terms):
        return None
    total = qparse.Term("area_total", None, 10 ** 6)
    if letter == "G" and len(apts) == 1:  # floor total minus apartment X
        return qparse.Query("area", "diff", [qparse.Term("area_total", None, -1), apts[0]], qr.unit, qr.notes,
                            include_outdoor=qr.include_outdoor)
    if letter == "C" and len(apts) == 2:  # ratio, first named / second named
        return qparse.Query("area", "ratio", sorted(apts, key=lambda t: t.pos), None, qr.notes)
    if letter == "D" and len(apts) == 1:  # share of the floor total in %
        return qparse.Query("area", "pct", [apts[0], total], "%", qr.notes, include_outdoor=qr.include_outdoor)
    return None


def _known_template(question: str) -> bool:
    try:
        from stoa.router.prior import known_template
        return known_template(question)
    except Exception:  # noqa: BLE001 - no train split available: treat as unseen
        return False


def _opcheck(question: str, backend: str = "local") -> str | None:
    """One short LLM call: which operation does the question ask (letter A-K)? None if the LLM is unavailable."""
    try:
        from stoa.llm import chat
        r = chat(OPCHECK_PROMPT.replace("{q}", question), backend=backend, max_tokens=3, temperature=0.0)
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"\b([A-K])\b", (r.text or "").strip().upper())
    return m.group(1) if m else None


_EACH_W = r"(?:per|each|every|for\s+each|for\s+every|a|an|one|a\s+single|any|je|pro|par|chaque|ogni|cada|jede[rnms]?|une?|ein(?:e)?)"
_UNIT_ASK = re.compile(r"\b(?:what|how\s+much)\s+(?:does|would|will|is)\s+(?:one|a|each|a\s+single|every|the\s+average)\b|"
                       r"\bper\s+(?:door|window|unit|piece|item)\s*\?\s*$|\bcost\s+per\b", re.I)


def _price(question: str, qr: qparse.Query) -> tuple[float, str, str] | None:
    """A stated price or rate the answer is multiplied by: '1,200 euros per door', 'each door costs …', 'si chaque
    fenêtre coûte 650 €', '45 euros per m²' -> (factor, unit, why), or None. Detection reuses W1's ifc arith module
    (stoa/solvers/ifc/arith.py); a fallback covers fixtures it has no kind for ('450 euros per washbasin'). Only for a
    single count kind or an area (Q 08:30/08:55: table-QA code multiplied ALL objects in 2 of 5 runs)."""
    if not qr.terms or qr.op != "sum" or _UNIT_ASK.search(question):
        return None
    try:
        from stoa.solvers.ifc.arith import _CUR, currency, detect, text_of
        o = detect(question)
        t = text_of(question)
    except Exception:  # noqa: BLE001 - module missing or changed: no price path
        return None
    one_kind = qr.qtype == "count" and len(qr.terms) == 1 and qr.terms[0].kind == "count"
    if o is not None and o.op == "mul" and o.n:
        if o.basis == "count" and one_kind and o.basis_kind in (None, qr.terms[0].arg):
            return float(o.n), o.unit or "count", o.why
        if o.basis == "area" and qr.qtype == "area" and o.basis_unit in (None, "m2", "ft2") and o.unit:
            if o.basis_unit == "ft2":
                qr.unit = "ft2"
            return float(o.n), o.unit, o.why
    cur = currency(t)
    if cur and one_kind:
        kw = "|".join(qparse.KIND_WORDS.get(qr.terms[0].arg, []))
        amt = r"(?:" + _CUR + r"\s*)?(\d+(?:\.\d+)?)\s*(?:" + _CUR + r")?"
        for rx in (amt + r"\s*" + _EACH_W + r"\s+(?:" + kw + r")\b",
                   r"\b" + _EACH_W + r"\s+(?:" + kw + r")\b[^.?;]{0,30}?" + amt):
            for m in re.finditer(rx, t):
                if re.search(_CUR, m.group(0)) and (n := next((float(g) for g in m.groups()
                                                             if g and re.fullmatch(r"\d+(?:\.\d+)?", g)), None)):
                    return n, cur, f"price {n:g} {cur} per {qr.terms[0].arg}"
    return None


def _outdoor_only_exclusion(question: str) -> bool:
    """Every exclusion clause of the question names only outdoor spaces or shafts (no apartment, room or label)."""
    ql = question.lower()
    spans = [m.group(0) for m in re.finditer(qparse.EXCL_CLAUSE, ql)] + [m.group(0) for m in re.finditer(qparse.POST_EXCL, ql)]
    if not spans:
        return False
    for sp in spans:
        rest = re.sub(qparse._OUT_N + r"|\b(?:and|or|und|oder|et|ou|e|o|the|die|les|i|le|gli|all|any|excluding|except|"
                      r"without|not|counting|excluded|ohne|hors|sans|senza|esclus\w*|exclu\w*|ausgenommen|nicht|"
                      r"mitgerechnet|in|m²|m2|voids?|vides?|lufträume?)\b|[,.()]", " ", sp)
        if rest.strip():
            return False
    return True


def _substitute_kind(question: str, code: str) -> str | None:
    """The table-QA code filters objects of a kind the question never names (a substitute class), else None."""
    kinds = re.findall(r"""\[['"]kind['"]\]\s*==\s*['"](\w+)['"]|kind\s*==\s*['"](\w+)['"]""", code)
    kinds = {a or b for a, b in kinds}
    for m in re.finditer(r"""\[['"]kind['"]\]\.isin\(\[([^\]]*)\]""", code):
        kinds |= set(re.findall(r"""['"](\w+)['"]""", m.group(1)))
    kinds = {k for k in kinds if k in qparse.KIND_WORDS}
    if not kinds:
        return None
    ql = question.lower()
    named = {k for k in kinds if qparse._find_words(qparse.KIND_WORDS[k], ql)}
    if named or ("washbasin" in kinds and re.search(r"\bsinks?\b", ql)) or re.search(
            r"sanit\w*|fixtures?|plumbing|objects?|items?|elements?|openings?|symbols?|apparecchi|ouvertures?|"
            r"öffnungen|aperture|einrichtung\w*|wet\s+rooms?", ql):
        return None  # a group word covers several kinds ("sanitary fixtures", "openings")
    return sorted(kinds)[0]


def _same_number(tok: str, n: float) -> bool:
    for c in (tok.replace(",", ""), tok.replace(".", "").replace(",", "."), tok.replace(",", "."), tok.replace("'", "")):
        try:
            if abs(float(c) - n) < 1e-9:
                return True
        except ValueError:
            pass
    return False


WHICH_APT = (r"^\s*(?:which|what|in\s+which|welche[rs]?|in\s+welcher|quel(?:le)?|dans\s+quel|quale|in\s+quale|welk(?:e)?)\s+"
             r"(?:apartment|flat|unit|dwelling|wohnung|wohneinheit|appartement|logement|appartamento|woning)\b")


def _echo(question: str, value) -> str | None:
    """The table-QA answer is just an entity (or number) the question itself names, and the only one of its kind
    there (so 'which is larger, apartment A or B' -> 'apartment A' is not an echo)."""
    q = qparse._norm(question)
    if isinstance(value, str):
        v = value.strip().lower()
        apts = {f"apartment {a}".lower() for m in qparse.APT_RE.finditer(q) for a in re.split(qparse.JOIN, m.group(1)) if a}
        if v in apts and len(apts) == 1:
            return "the apartment"
        rooms = {m.group(1) for m in qparse.ROOMNUM_RE.finditer(q)}
        if len(rooms) == 1 and any(v == rn or v.startswith(f"room {rn}".lower()) or v == f"room {rn}" for rn in rooms):
            return "the room"
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        nums = {float(n.replace(",", ".")) for n in re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])", q)
                if not qparse.ROOMNUM_RE.fullmatch(n)}
        if float(value) in nums and float(value) != 0:
            return "a number"
    return None


def _in_tables(value: str, tables: dict) -> bool:
    """A text answer is grounded when it is yes/no, an apartment/room reference, or occurs in some table cell."""
    v = value.strip().lower()
    if v in ("yes", "no") or re.fullmatch(r"(?:apartment|room)\s+\S+(?:\s*\(.*\))?", v):
        return True
    for df in tables.values():
        for col in df.columns:
            if df[col].dtype == object and df[col].astype(str).str.lower().str.contains(re.escape(v), regex=True).any():
                return True
    return False


def _translate(question: str, backend: str = "local"):
    """stoa.llm.to_english for languages outside en/fi/de/fr/it (one local LLM call; names and numbers are masked
    and restored byte-identical). None when nothing was translated or a name/number was lost."""
    try:
        from stoa.llm import to_english
        tr = to_english(question, backend=backend)
    except Exception:  # noqa: BLE001 - server down: answer on the original
        return None
    return tr if tr.translated and tr.ok else None


BEDROOM_FALLBACK = ["Zimmer", "Pièce", "Stanza"]


def _bedroom_fallback(fm: FloorModel, t: qparse.Term, names: list[str]) -> tuple[list[str], str | None]:
    """Many Swiss plans label bedrooms just 'Zimmer'/'Pièce'/'Stanza' (no 'Schlafzimmer'): use those, and say so."""
    if not t.note.startswith("concept bedroom") or _rooms_with_name(fm, names):
        return names, None
    if _rooms_with_name(fm, BEDROOM_FALLBACK):
        return BEDROOM_FALLBACK, ("no room is labelled as a bedroom (Schlafzimmer/Chambre à coucher/Camera da letto); "
                                  "counted the rooms labelled 'Zimmer'/'Pièce'/'Stanza' as bedrooms")
    return names, None


def _in_scope(fm: FloorModel, kind: str, bbox, scope: list[str] | None) -> bool:
    """Is an object inside one of the scoped apartments? Fixtures: centre in the UNIT_OUTLINE; doors/windows sit
    in walls, so they count when they touch the outline buffered by 0.3 m (an entrance door counts for the flat)."""
    if not scope:
        return True
    from shapely.geometry import Point
    from shapely.geometry import box as sbox

    b = sbox(*bbox)
    for u in fm.units:
        if (u.label in scope or "*" in scope) and u.poly is not None:
            if kind in ("door", "window"):
                if u.poly.buffer(0.3).intersects(b):
                    return True
            elif u.poly.contains(Point(b.centroid.x, b.centroid.y)):
                return True
    return False


def _eval_term(fm: FloorModel, t: qparse.Term, qr: qparse.Query) -> _Part:
    k = t.kind
    if k == "count":
        kind = t.arg
        if kind == "apartment":
            boxes = [((u.text.bbox if u.text else u.bbox), f"apartment {u.label}") for u in fm.units]
            return _Part(len(fm.units), RULE_CONF["count:apartment"], boxes,
                         [f"apartments = {len(fm.units)} labels {sorted(u.label for u in fm.units)}"],
                         [f"counted {KIND_DESC['apartment']}"])
        if fm.supported is not None and kind not in fm.supported:
            return _Part(None, 0.0, [], [f"{kind}s are not identified in this (PDF-only) model"],
                         missing=[f"{kind} symbols: not separable by style in the PDF; needs the DXF or a detector"])
        items = fm.items.get(kind, [])
        if t.scope:
            items = [it for it in items if _in_scope(fm, kind, it.bbox, t.scope)]
            missing = [] if all(u.poly is not None for u in fm.units if u.label in t.scope or "*" in t.scope) else \
                [f"no UNIT_OUTLINE for apartment(s) {t.scope}"]
            how = ("objects touching the UNIT_OUTLINE (±0.3 m)" if kind in ("door", "window")
                   else "objects whose centre lies inside the UNIT_OUTLINE")
            where = "all apartments (not the common areas)" if "*" in t.scope else f"apartment(s) {', '.join(t.scope)}"
            asm = [f"counted {KIND_DESC[kind]}", f"restricted to {where}: {how}"]
            return _Part(len(items), 0.8 if kind in ("door", "window") else 0.9, [(it.bbox, it.note) for it in items],
                         [f"{kind}s in apartment(s) {t.scope} = {len(items)}"], asm, missing)
        n = window_count(fm) if kind == "window" else len(items)
        tr = [f"{kind}s = {n} ({KIND_DESC[kind]})"]
        if kind == "window" and n != len(items):
            tr.append(f"window boxes grouped into {len(items)} clusters; count uses polylines/3")
        conf, asm = RULE_CONF[f"count:{kind}"], [f"counted {KIND_DESC[kind]}"]
        if fm.supported is not None and kind == "window":  # PDF-only model
            conf = 0.5
            asm = ["PDF-only: windows = touching frame-rectangle + glass-line groups outside every room polygon, "
                   "lines / 3 (matched the DXF count on 19/25 floors; tends to overcount)"]
        elif fm.supported is not None:
            asm = [f"PDF-only: {kind}s identified by path shape/style (matched the DXF on 25/25 floors)"]
        return _Part(n, conf, [(it.bbox, it.note) for it in items], tr, asm)
    if k == "count_label":
        if t.arg == "<numbered>":
            if t.scope:  # "how many rooms does apartment B have": numbered indoor rooms inside its outline
                rooms = [r for r in fm.rooms if r.number and r.unit in t.scope and not r.outdoor and not r.shaft]
                out = [r for r in fm.rooms if r.number and r.unit in t.scope and (r.outdoor or r.shaft)]
                named = [r for r in rooms if r.name]
                return _Part(len(rooms), 0.6, [(r.bbox, _room_note(r)) for r in rooms],
                             [f"numbered indoor rooms in apartment(s) {t.scope} = {len(rooms)}"
                              + (f" (not counted: {', '.join(r.label() for r in out)})" if out else "")],
                             [f"'rooms' read as every numbered indoor room of apartment(s) {', '.join(t.scope)} (bath, "
                              f"corridor and storage included; balconies excluded); {len(named)} of them carry a name"])
            rooms = [r for r in fm.rooms if r.number]
            return _Part(len(rooms), 0.5, [(r.bbox, _room_note(r)) for r in rooms],
                         [f"rooms with a number = {len(rooms)}"], ["'rooms' read as every numbered room polygon"])
        names = t.arg if isinstance(t.arg, list) else [t.arg]
        names, fb = _bedroom_fallback(fm, t, names)
        texts = [tx for tx in fm.texts if tx.text in names] or [tx for tx in fm.texts if tx.text.lower() in {n.lower() for n in names}]
        if t.scope:
            in_rooms = {id(tx): r for r in fm.rooms for tx in r.texts}
            texts = [tx for tx in texts if (r := in_rooms.get(id(tx))) is not None and r.unit in t.scope]
        boxes = []
        for tx in texts:
            room = next((r for r in fm.rooms if tx in r.texts), None)
            boxes.append((room.bbox if room else tx.bbox, f"'{tx.text}'" + (f" room {room.number}" if room and room.number else "")))
        conf = RULE_CONF["count_label"] * (0.7 if t.note.startswith("concept") else 1.0)
        asm = [f"{t.note}: labels {names}"] if t.note else []
        if fb:
            conf, asm = 0.5, asm + [fb]
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
    if k == "rooms":  # a superlative over a set of rooms: "the largest room (in apartment B / labelled X)"
        names = t.arg if isinstance(t.arg, list) or t.arg is None else [t.arg]
        fb = None
        if names is not None:
            names, fb = _bedroom_fallback(fm, t, names)
            cands = _rooms_with_name(fm, names)
        else:
            cands = [r for r in fm.rooms if r.number and not r.shaft and (qr.include_outdoor or not r.outdoor)]
        if t.scope:
            cands = [r for r in cands if r.unit in t.scope]
        unnamed = [r for r in cands if not r.name]
        if names is None and unnamed and len(unnamed) < len(cands):
            # numbered polygons without a name are mostly ducts/shafts/niches (< 1 m²): not what "a room" means
            cands = [r for r in cands if r.name]
        if not cands:
            return _Part(None, 0.0, [], [f"no rooms match {names or 'numbered rooms'} in scope {t.scope}"],
                         missing=["no matching room on this floor"])
        ranked = sorted(cands, key=lambda r: r.net, reverse=(qr.op == "max"))
        r = ranked[0]
        tr = [f"{qr.op} over {len(cands)} rooms ({t.note}{', apartment ' + ','.join(t.scope) if t.scope else ''}): "
              + ", ".join(f"{x.label()} {x.net:.2f}" for x in ranked[:4])]
        conf = 0.9
        if len(ranked) > 1 and abs(ranked[1].net - r.net) <= 0.02 * max(r.net, 1e-9):
            conf = 0.5
            tr.append(f"tie within 2%: {r.label()} vs {ranked[1].label()}")
        asm = [f"candidates: {t.note}" + (f" in apartment(s) {', '.join(t.scope)}" if t.scope else "")
               + ("; outdoor rooms excluded" if names is None and not qr.include_outdoor else "")
               + (f"; {len(unnamed)} numbered polygons without a room name (ducts/niches) ignored"
                  if names is None and unnamed and len(cands) < len(unnamed) + len(cands) and all(c.name for c in cands) else "")]
        if fb:
            conf, asm = min(conf, 0.5), asm + [fb]
        p = _Part(r.net, conf * (0.85 if t.note.startswith("concept") else 1.0), [(r.bbox, _room_note(r))], tr, asm)
        p.room = r
        return p
    if k == "area_label":
        names = t.arg if isinstance(t.arg, list) else [t.arg]
        names, fb = _bedroom_fallback(fm, t, names)
        rooms = _rooms_with_name(fm, names)
        if t.scope:  # "the kitchen in apartment A"
            rooms = [r for r in rooms if r.unit in t.scope]
        val = sum(r.net for r in rooms)
        asm = ["net floor area = sum of ROOM_OUTLINE polygon areas"] + ([f"{t.note}: labels {names}"] if t.note else [])
        if t.scope:
            asm.append(f"restricted to rooms inside apartment(s) {', '.join(t.scope)}")
        if fb:
            asm.append(fb)
        conf = RULE_CONF["area_label"] * (0.7 if t.note.startswith("concept") else 1.0) * (0.95 if t.scope else 1.0)
        if fb or (t.scope and not rooms):
            conf = min(conf, 0.5)
        return _Part(val, conf, [(r.bbox, _room_note(r)) for r in rooms],
                     [f"{len(rooms)} rooms labelled {names}: " + " + ".join(f"{r.net:.2f}" for r in rooms)], asm)
    if k == "area_apartment":
        unit = next((u for u in fm.units if u.label == t.arg), None)
        if unit is None:
            return _Part(None, 0.0, [], [f"apartment {t.arg} not found; labels {[u.label for u in fm.units]}"],
                         missing=[f"no 'Whg./App. {t.arg}' label on this floor"])
        if qr.gross and unit.poly is not None:
            val = unit.poly.area
            return _Part(val, 0.25, [(unit.bbox, f"apartment {t.arg} outline {val:.2f} m²")],
                         [f"apartment {t.arg}: UNIT_OUTLINE polygon area {val:.2f} m² (asked: gross)"],
                         ["gross floor area is not in the DXF; returned the apartment outline area (≈ net + partitions, "
                          "median 1.02 x the rooms' net area); exterior walls not included"],
                         ["wall thickness / gross-area standard (e.g. SIA 416 GF) to add the walls"])
        rooms = [r for r in fm.rooms if r.unit == t.arg and r.number and (qr.include_outdoor or not r.outdoor)]
        excl = [r for r in fm.rooms if r.unit == t.arg and ((r.outdoor and not qr.include_outdoor) or not r.number)]
        val = sum(r.net for r in rooms)
        tr = [f"apartment {t.arg}: {len(rooms)} numbered indoor rooms inside its UNIT_OUTLINE = {val:.2f} m²"]
        if excl:
            tr.append("excluded: " + ", ".join(r.label() for r in excl))
        asm = ["apartment = rooms whose label lies inside the UNIT_OUTLINE holding 'Whg./App. X'",
               "outdoor rooms (Balkon/Loggia/Terrasse/…) " + ("INCLUDED (asked)" if qr.include_outdoor else "excluded")]
        conf, asm2, miss = _unnamed_caveat(rooms, val)
        return _Part(val, min(conf, RULE_CONF["area_apartment"]) if unit.poly is not None else 0.3,
                     [(r.bbox, _room_note(r)) for r in rooms], tr, asm + asm2, miss)
    if k == "area_total":
        rooms = [r for r in fm.rooms if r.number and (qr.include_outdoor or not r.outdoor) and not r.shaft]
        excl = [r for r in fm.rooms if r.number and ((r.outdoor and not qr.include_outdoor) or r.shaft)]
        val = sum(r.net for r in rooms)
        tr = [f"{len(rooms)} numbered indoor rooms = {val:.2f} m²"]
        if excl:
            tr.append("excluded outdoor/shaft: " + ", ".join(r.label() for r in excl))
        asm = ["total = numbered ROOM_OUTLINE polygons, minus shafts and "
               + ("NOT minus outdoor rooms (asked to include them)" if qr.include_outdoor else
                  "minus outdoor rooms (Balkon/Loggia/Terrasse/…)")]
        if qr.gross:
            asm.append("gross area asked but walls are not modelled: this is the net total (an underestimate)")
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
    a = sum(r.net for r in un)
    lo = total - a
    share = a / total if total else 0
    conf = 0.95 if share < 0.02 else 0.8
    return conf, [f"included {len(un)} numbered rooms without a name ({a:.2f} m²: "
                  + ", ".join(r.number for r in un[:8]) + "); without them the total is "
                  + f"{lo:.2f} m²"], ["room type of unnamed numbered rooms (shaft/void or storage?)"]


class _Mapper:
    """DXF bbox -> Evidence on the asked file (PDF points or PNG pixels); falls back to the PDF sibling."""

    def __init__(self, path: str, dxf_rel: str, tf=None):
        self.path = path
        sib = siblings(path)
        ext = Path(path).suffix.lower()
        self.pdf_rel = path if ext == ".pdf" else sib.get(".pdf")
        self.tf = tf
        self.file, self.space, self.k = None, None, 1.0
        if self.pdf_rel and self.tf is None and dxf_rel.lower().endswith(".dxf"):
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

    def __init__(self, llm: int | str = 1, backend: str = "local", opcheck: int | str = 1, **kwargs):
        self.opcheck = int(opcheck)
        super().__init__(**kwargs)
        self.llm = bool(int(llm))
        self.backend = backend

    def can_handle(self, path: str, question: str) -> bool:
        if source_of(path) != "swiss_dwellings" and Path(path).suffix.lower() != ".dxf":
            return False
        return Path(path).suffix.lower() == ".dxf" or abspath(str(Path(path).with_suffix(".dxf"))).exists()

    def _load(self, path: str):
        """-> (FloorModel, source file it came from, Transform metres->pdf_pt or None to fit) or (None, reason, None)."""
        dxf_rel = path if path.lower().endswith(".dxf") else siblings(path).get(".dxf")
        if not dxf_rel:
            return None, "no DXF sibling", None
        return load_floor(str(abspath(dxf_rel))), dxf_rel, None

    # "the whole building" on a plan of ONE floor (every swiss_dwellings building in the data has exactly one floor
    # drawn: 1,040 buildings x 1 floor). Q 04:58/08:45: 36 doors @0.99 for "in the whole building".
    BUILDING_W = re.compile(
        r"\b(?:whole|entire|complete) (?:building|house)\b|\ball (?:the )?(?:floors|storeys|stories|levels)\b|"
        r"\bevery (?:floor|storey|story|level)\b|\b(?:does|do) the building have\b|\bthe building (?:as a whole|in total)\b|"
        r"\b(?:ganzen?|gesamten?|komplette[nm]?) (?:Gebäude|Haus)|\balle[nm]? (?:Geschosse|Stockwerke[n]?|Etagen)\b|"
        r"\b(?:tout le|l'ensemble du) bâtiment|\bbâtiment (?:entier|complet)|\btous les étages\b|"
        r"\b(?:l')?intero edificio|\btutto l'edificio|\bedificio intero|\btutti i piani\b|"
        r"\b(?:het )?(?:hele|gehele) (?:gebouw|pand)|\balle verdiepingen\b|\bhela (?:byggnaden|huset)\b|\balla våningar\b|"
        r"\bkoko (?:rakennu|talo)|\bkaikki(?:ssa)? kerrok|\btodo el edificio\b|\bedificio (?:entero|completo)\b|"
        r"\btodas las plantas\b|\btodos los pisos\b", re.I)

    def solve(self, path: str, question: str) -> Answer:
        ans = self._solve_guarded(path, question)
        if ans.value is not None and (self.BUILDING_W.search(question) or
                                      any(self.BUILDING_W.search(str(t)) for t in ans.assumptions[:1])):
            m = re.search(r"site(\d+)_bldg(\d+)_floor(\d+)", path)
            floors = sorted({re.search(r"_floor(\d+)", f).group(1) for f in
                             (os.listdir(abspath(path).parent) if m else [])
                             if f.startswith(f"site{m.group(1)}_bldg{m.group(2)}_floor")}) if m else []
            if len(floors) <= 1:
                where = f"floor {m.group(3)} of building {m.group(2)}" if m else "one floor"
                ans.confidence = round(min(ans.confidence, 0.5), 3)
                ans.assumptions = [*ans.assumptions, f"only {where} is drawn (no other floor of this building is in "
                                                     "the data); the answer counts this floor only"]
                ans.missing = [*ans.missing, "the other floors of the building are not in the data, so the whole-building "
                                             "total is unknown"]
                ans.trace.append("guard: the question asks about the whole building, the data has one floor -> conf <= 0.5")
        return ans

    def _solve_guarded(self, path: str, question: str) -> Answer:
        """Translate-first for languages the rules were never written for (S0/F 04:05: the sealed hard2r drop is
        language), then the rule/table-QA answer, then guards that check the answer fits what was asked."""
        tr = _translate(question, self.backend) if self.llm else None
        q = tr.text if tr is not None else question
        ans = self._solve(path, q)
        if tr is not None:
            ans.trace.insert(0, tr.note)
            ans.assumptions = [tr.note, *ans.assumptions]
            ans.confidence = round(min(ans.confidence, 0.85), 3)  # a translated wording is never a known template
        if ans.value is None:
            return ans
        if (m := qparse.ATTR_W.search(q)) is not None:
            ans.confidence = round(min(ans.confidence, 0.2), 3)
            ans.missing = [*ans.missing, f"the question asks about '{m.group(0)}', which a 2D floor-plan DXF does not "
                                         "record (only room outlines, labels, doors, windows, fixtures); the value "
                                         "answers something else"]
            ans.trace.append(f"guard: property word '{m.group(0)}' not in the drawing -> confidence <= 0.2")
        elif ans.unit == "count" and not re.search(qparse.COUNT_WORDS, q.lower()):
            ans.confidence = round(min(ans.confidence, 0.3), 3)
            ans.missing = [*ans.missing, "the answer is a count, but the question has no counting word (how many / "
                                         "number of …); it may ask for something else"]
            ans.trace.append("guard: count answer without a counting cue -> confidence <= 0.3")
        return ans

    def _solve(self, path: str, question: str) -> Answer:
        fm, dxf_rel, tf0 = self._load(path)
        if fm is None:
            return self.abstain(dxf_rel)
        self._tf0 = tf0
        vocab = fm.names() + KNOWN_NAMES
        qr = qparse.parse(question, vocab, room_numbers={r.number for r in fm.rooms if r.number})
        trace = [f"parsed: {qr.describe()}", *[f"parse note: {n}" for n in qr.notes]]
        opcheck_cap = opcheck_rewrite = False
        price = _price(question, qr)
        cq = question
        if price is not None:
            trace.append(f"stated price/rate: {price[2]} -> answer = {price[0]:g} x the quantity from the rules")
            kw = "|".join(qparse.KIND_WORDS.get(qr.terms[0].arg, ["door"])) if qr.qtype == "count" else r"m²|m2|square\s+\w+"
            cq = re.sub(r"\b(?:each|every|one|chaque|jede[rnms]?|ogni|cada|any)\b|\bper\s+(?:" + kw + ")", " ", question, flags=re.I)
        if self.llm and not qparse.covered(cq, qr):
            ans = self._tableqa(path, dxf_rel, fm, question, trace)
            if ans is not None:
                return ans
        elif self.llm and self.opcheck and price is None and not qr.op_sure and qr.terms and qr.op in ("sum", "diff") \
                and not _known_template(question):
            # unseen wording that the rules read as a plain value/sum/difference: one short LLM call checks the
            # operation (any language); on disagreement the table QA answers instead (F/S0 hard2p/hard2q lesson:
            # keyword rules miss reworded operators and then answer the simpler question confidently)
            letter = _opcheck(question, self.backend)
            neg = qr.op == "diff" and qr.terms[0].kind == "area_total"  # the floor-minus-apartment rule fired
            ok = letter is None or (qr.op == "sum" and letter == "A") or (qr.op == "diff" and (
                (letter == "B" and not neg) or (letter == "G" and neg)))
            if not ok and letter == "G" and qr.op == "sum" and _outdoor_only_exclusion(question):
                # W4 08:31: "net floor area of apartment A, excluding balconies, loggias and terraces" read as 'floor
                # minus apartment A'; balconies are never in a net area, so the exclusion changes nothing
                ok = True
                trace.append("operation check: the excluded part is only balconies/loggias/terraces/shafts, which the "
                             "net area never contains -> the rules' sum stands")
            trace.append(f"operation check (LLM): '{letter}' = {OPCHECK_KINDS.get(letter, '?')}; rules applied "
                         f"{qr.op} -> {'agree' if ok else 'disagree'}")
            if not ok and (rw := _rewrite_by_op(qr, letter)) is not None:
                # the LLM named the operation; the rules compute it on the parts they already found
                trace.append(f"rewritten by the operation check: {qr.describe()} -> {rw.describe()}")
                qr = rw
                opcheck_rewrite = True
            elif not ok:
                ans = self._tableqa(path, dxf_rel, fm, question, trace)
                if ans is not None:
                    return ans
                opcheck_cap = True
        if not qr.terms:
            return Answer.abstain(self.name, "question not understood by the DXF parser", trace)
        if any(t.kind == "area_room" and t.arg == "<all>" for t in qr.terms):  # every numbered indoor room
            t0 = qr.terms[0]
            rs = [r for r in fm.rooms if r.number and not r.shaft and (qr.include_outdoor or not r.outdoor)
                  and (not t0.scope or r.unit in t0.scope)]
            qr.terms = [qparse.Term("area_room", r.number, k, note=t0.note) for k, r in enumerate(rs)]
            trace.append(f"over {len(rs)} numbered indoor rooms" + (f" of apartment(s) {t0.scope}" if t0.scope else ""))
        if any(t.kind == "area_apartment" and t.arg == "<all>" for t in qr.terms):  # every apartment on the floor
            t0 = qr.terms[0]
            qr.terms = [qparse.Term("area_apartment", u.label, k, note=t0.note)
                        for k, u in enumerate(sorted(fm.units, key=lambda u: u.label))]
            trace.append(f"over all apartments: {[t.arg for t in qr.terms]}")
            if not qr.terms:
                return Answer(value=None, unit=qr.unit, confidence=0.0, solver=self.name,
                              trace=trace + ["no 'Whg./App.' apartment labels on this floor"],
                              missing=["no apartments identified on this floor"])
        if qr.op in ("count_gt", "count_lt", "count_ge") and any(t.kind == "area_label" for t in qr.terms):
            # "how many of the kitchens are larger than 7.5 m²": each labelled room against the threshold, not their sum
            new_terms = []
            for t in qr.terms:
                if t.kind != "area_label":
                    new_terms.append(t)
                    continue
                rs = [r for r in _rooms_with_name(fm, t.arg) if r.number and (qr.include_outdoor or not r.outdoor)
                      and (not t.scope or r.unit in t.scope)]
                new_terms += [qparse.Term("area_room", r.number, t.pos + k, note=t.note) for k, r in enumerate(rs)]
            trace.append(f"threshold over each labelled room: {[t.arg for t in new_terms]}")
            qr.terms = new_terms
            if not qr.terms:
                return Answer(value=0, unit="count", confidence=0.35, solver=self.name, trace=trace,
                              missing=["no room with that label on this floor"])
        parts = [_eval_term(fm, t, qr) for t in qr.terms]
        for t, p in zip(qr.terms, parts):
            trace += p.trace
        assumptions = [a for p in parts for a in p.assumptions]
        missing = [m for p in parts for m in p.missing]
        vals = [p.value for p in parts]
        known = [v for v in vals if v is not None]
        if not known:
            return Answer(value=None, unit=qr.unit, confidence=0.0, solver=self.name, trace=trace + ["abstain: no term resolved"],
                          missing=missing or ["nothing matched on this floor"])
        if qr.qtype == "area" and qr.op == "sum" and qr.terms and all(t.kind == "area_label" for t in qr.terms) and \
                not any(p.boxes for p in parts):
            # "How big is the Ripostiglio?" on a floor without one was 0 m² at 0.98: a false premise, not an area
            names = sorted({r.name for r in fm.rooms if r.name})
            asked = qr.terms[0].arg if isinstance(qr.terms[0].arg, str) else qr.terms[0].note
            return Answer(value=None, unit=qr.unit, confidence=0.0, solver=self.name,
                          trace=trace + [f"no room labelled {asked!r} on this floor"],
                          missing=[f"no room labelled '{asked}' on this floor (labels here: {', '.join(names[:15])})"])
        conf = 1.0
        for p in parts:
            conf *= p.conf if p.value is not None else 0.2
        if opcheck_rewrite:
            conf = min(conf, 0.7)
            assumptions.append("the operation (difference / ratio / share) was identified by a language model; "
                               "the numbers come from the DXF rules")
        elif qparse.operator_unapplied(question, qr) or opcheck_cap:
            conf = min(conf, 0.3)  # S0 D9: low enough that the pipeline's agent takes over
            missing.append("the question mentions an operation (average/ratio/share/threshold/per/'not in') that the "
                           "rule parser did not apply; the value may answer a simpler question")
        # combine --------------------------------------------------------------------------------
        value: float | int | str
        unit = qr.unit
        if qr.qtype == "text" and len(parts) == 1 and qr.terms[0].kind == "rooms":
            r = parts[0].room
            value = f"room {r.number}" + (f" ({r.name})" if r.name else "") if r.number else (r.name or r.label())
            if r.unit and re.search(WHICH_APT, question, re.I):  # "which apartment has the largest balcony"
                value = f"apartment {r.unit}"
                trace.append(f"the question asks for the apartment: room {r.number} is in apartment {r.unit}")
            trace.append(f"{qr.op}: {r.label()} with {r.net:.2f} m²")
            unit = None
        elif qr.qtype == "text" and qr.op in ("max", "min"):
            pairs = [(v, t) for v, t in zip(vals, qr.terms) if v is not None]
            v, t = (max if qr.op == "max" else min)(pairs, key=lambda vt: vt[0])
            value = str(t.arg if not isinstance(t.arg, list) else t.arg[0])
            if t.kind == "area_label" and t.scope and len(t.scope) == 1:  # "which apartment has the bigger kitchen"
                value = f"apartment {t.scope[0]}"
            elif t.kind == "area_apartment":
                value = f"apartment {value}"
            elif t.kind in ("area_room", "rooms"):
                r = getattr(p, "room", None) if t.kind == "rooms" else next((r for r in fm.rooms if r.number == t.arg), None)
                value = f"room {value}" + (f" ({r.name})" if r is not None and r.name else "")
            trace.append(f"{qr.op}: " + ", ".join(f"{tt.arg}={vv:.2f}" for vv, tt in pairs) + f" -> {value}")
            unit = None
        elif qr.op in ("max", "min") and len(known) > 1:  # "the area of the largest apartment"
            pairs = [(v, t) for v, t in zip(vals, qr.terms) if v is not None]
            v, t = (max if qr.op == "max" else min)(pairs, key=lambda vt: vt[0])
            value = v
            trace.append(f"{qr.op}: " + ", ".join(f"{tt.arg}={vv:.2f}" for vv, tt in pairs) + f" -> {t.arg}")
        elif qr.op == "mean":
            if len(parts) == 1 and parts[0].boxes and "over all apartments" not in qr.terms[0].note:
                # average over the rooms of one label
                value = known[0] / len(parts[0].boxes)
                trace.append(f"mean: {known[0]:.2f} / {len(parts[0].boxes)} rooms = {value:.2f}")
            else:
                value = sum(known) / len(known)
                trace.append(f"mean of {[round(v, 2) for v in known]} = {value:.2f}")
        elif qr.op == "ratio":
            if len(known) < 2 or not known[1]:
                return Answer(value=None, unit=None, confidence=0.0, solver=self.name, trace=trace + ["ratio: missing/zero divisor"],
                              missing=missing or ["divisor not found"])
            value = round(known[0] / known[1], 3)
            trace.append(f"ratio: {known[0]:.2f} / {known[1]:.2f} = {value}")
        elif qr.op == "pct":
            if len(known) < 2 or not known[1]:
                return Answer(value=None, unit="%", confidence=0.0, solver=self.name, trace=trace + ["share: missing total"],
                              missing=missing or ["floor total not found"])
            value = round(100.0 * known[0] / known[1], 2)
            trace.append(f"share: 100 × {known[0]:.2f} / {known[1]:.2f} = {value} %")
        elif qr.op in ("pctdiff", "pctdiff_less"):
            if len(known) < 2 or not known[1]:
                return Answer(value=None, unit="%", confidence=0.0, solver=self.name,
                              trace=trace + ["relative difference: missing reference"], missing=missing or ["reference not found"])
            a, b = known[0], known[1]  # subject, reference ("A larger than B": (A − B) / B)
            value = round(100.0 * ((a - b) if qr.op == "pctdiff" else (b - a)) / b, 2)
            trace.append(f"relative difference: 100 × ({a:.2f} − {b:.2f}) / {b:.2f} = {value} %" if qr.op == "pctdiff" else
                         f"relative difference: 100 × ({b:.2f} − {a:.2f}) / {b:.2f} = {value} %")
        elif qr.op in ("yes_gt", "yes_lt"):
            a = known[0]
            b = known[1] if len(known) > 1 else qr.threshold
            if b is None or len(known) < len(qr.terms):
                return Answer(value=None, unit=None, confidence=0.0, solver=self.name, trace=trace + ["comparison: a side is missing"],
                              missing=missing or ["one side of the comparison was not found"])
            yes = a > b if qr.op == "yes_gt" else a < b
            value, unit = ("yes" if yes else "no"), None
            trace.append(f"comparison: {a:.2f} {'>' if qr.op == 'yes_gt' else '<'} {b:.2f} -> {value}")
        elif qr.op in ("count_gt", "count_lt", "count_ge"):
            cmp = {"count_gt": lambda v: v > qr.threshold, "count_lt": lambda v: v < qr.threshold,
                   "count_ge": lambda v: v >= qr.threshold}[qr.op]
            hits = [t.arg for v, t in zip(vals, qr.terms) if v is not None and cmp(v)]
            value = len(hits)
            trace.append(f"{qr.op} {qr.threshold}: " + ", ".join(f"{t.arg}={v:.2f}" for v, t in zip(vals, qr.terms)
                                                              if v is not None) + f" -> {hits}")
            unit = "count"
        elif qr.op == "diff":
            value = known[0] - sum(known[1:])
            trace.append(f"difference: {' - '.join(str(round(v, 2)) for v in known)} = {value:.2f}")
            if qr.absolute and value < 0:
                value = -value
                trace.append("'difference between' is symmetric: reported as a positive number")
        elif qr.op == "list":  # two questions in one: one number per part
            names = [(t.note.replace("concept ", "") if t.note.startswith("concept") else
                      (t.arg if isinstance(t.arg, str) else "/".join(t.arg or []))) for t in qr.terms]
            value = "; ".join(f"{int(round(v))} {n}{'' if str(n).endswith('s') else 's'}" if v is not None else f"? {n}"
                              for v, n in zip(vals, names))
            unit = None
            trace.append(f"two questions in one: {value}")
        else:
            value = sum(known)
            if len(known) > 1:
                trace.append(f"sum: {' + '.join(str(round(v, 2)) for v in known)} = {value:.2f}")
        if qr.op == "ratio":
            unit = None
        elif qr.op in ("pct", "pctdiff", "pctdiff_less"):
            unit = "%"
        elif unit == "count":
            value = int(round(value))
        elif unit == "ft2":
            value = round(value * M2_TO_FT2, 2)
            assumptions.append("converted m² -> ft² (1 m² = 10.7639 ft²)")
        elif unit == "m2":
            value = round(value, 2)
        if price is not None and isinstance(value, (int, float)):
            base, base_unit = value, unit
            value, unit = round(price[0] * base, 2), price[1]
            trace.append(f"price x quantity: {price[0]:g} {unit} x {base} {base_unit} = {value}")
            assumptions.append(f"cost = the stated {price[2]} x {base} {base_unit} from the drawing")
            conf = min(conf, 0.95)
        # linked data: the PDF text layer is an independent rendering of the same drawing -> cross-check
        mapper = _Mapper(path, dxf_rel, tf0)
        if fm.supported is not None:
            trace.append(f"source: {fm.warnings[0] if fm.warnings else 'PDF-only model'}")
        if mapper.pdf_rel and fm.supported is None:  # cross-check only when the PDF is an independent source
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
        if qr.op == "sum" and len(qr.terms) == 1 and qr.terms[0].kind == "area_label" and len(parts[0].boxes) > 1 \
                and qparse.singular_label(question):
            conf = min(conf, 0.5)  # Q 04:50: "How big is the Küche?" with 8 kitchens -> their sum at 0.98
            rs = [(note.split(":")[0].replace("room ", ""), note) for _, note in parts[0].boxes]
            missing.append(f"{len(parts[0].boxes)} rooms match '{qr.terms[0].arg if isinstance(qr.terms[0].arg, str) else qr.terms[0].note}'"
                           f" on this floor; the value is their total. Name the room number or the apartment for one room")
            assumptions.append("several rooms match the singular name; answered their total: "
                               + "; ".join(n for _, n in parts[0].boxes[:8]))
            trace.append(f"singular name matches {len(parts[0].boxes)} rooms -> confidence <= 0.5")
        if (lost := qparse.unparsed_conjunct(question, qr)) is not None:
            conf = min(conf, 0.3)  # Q 04:48: "toilets and sinks" counted toilets only at 0.95
            missing.append(f"parsed only {qr.terms[0].kind} {qr.terms[0].arg!s}; could not read '{lost}'")
            trace.append(f"conjunction check: '{lost}' not parsed -> confidence <= 0.3")
        for n, asked in qparse.asked_room_names(question, qr, vocab).items():
            r = next((r for r in fm.rooms if r.number == n), None)
            if r is not None and not qparse.name_fits(r.name, asked):
                conf = min(conf, 0.3)  # Q red team: "room 2.23 ('Sauna')" where 2.23 is a Korridor was 0.99
                missing.append(f"room {n} on this plan is labelled '{r.name or 'without a name'}', not '{asked}'; "
                               "check the room number or the name")
                trace.append(f"name check: question calls room {n} '{asked}', the plan labels it "
                             f"'{r.name or '-'}' ✗ -> confidence <= 0.3")
            elif r is not None:
                trace.append(f"name check: room {n} '{asked}' fits the plan label '{r.name}' ✓")
        extra = [x for x in qparse.unused_numbers(question, qr) if price is None or not _same_number(x, price[0])]
        if extra:
            conf = min(conf, 0.3)  # F/S0: a stated price/rate/constant the rules did not apply -> the agent does it
            missing.append(f"the question states {', '.join(extra[:3])}, which this rule answer does not use (a price, "
                           "rate or factor?); the value is the base quantity before that arithmetic")
            trace.append(f"unused numbers in the question: {extra[:3]} -> confidence capped at 0.3")
        return Answer(value=value, unit=unit, confidence=round(min(max(conf, 0.0), 1.0), 3), evidence=evidence,
                      trace=trace, solver=self.name, assumptions=list(dict.fromkeys(assumptions)), missing=missing)

    @staticmethod
    def _cross_check(pdf_rel: str, fm: FloorModel, qr, parts, trace: list[str], conf: float) -> float:
        try:
            spans = pdf_span_counts(str(abspath(pdf_rel)))
        except Exception:  # noqa: BLE001
            return conf
        for t, p in zip(qr.terms, parts):
            if p.value is None or t.scope:  # the PDF text layer has no apartment scope to compare with
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
            elif t.kind in ("area_room", "rooms"):
                r = getattr(p, "room", None) if t.kind == "rooms" else next((r for r in fm.rooms if r.number == t.arg), None)
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
        mapper = _Mapper(path, dxf_rel, getattr(self, "_tf0", None))
        by_id = {r.idx: r for r in fm.rooms}
        evidence = [mapper.ev(by_id[i].bbox, _room_note(by_id[i])) for i in res["used"] if i in by_id]
        value, unit = res["value"], res.get("unit")
        yesno = bool(qparse.YESNO.match(question.strip()))
        if isinstance(value, bool) or (yesno and isinstance(value, (int, float))):
            trace.append(f"yes/no question; query returned {value!r}")
            value, unit = ("yes" if value else "no"), None
        if isinstance(value, str):
            unit = None
            # apartments are identified by a letter: answer "apartment B", not "B"
            if re.fullmatch(r"[A-Z]", value.strip()) and re.search(
                    r"apartment|wohnung|appartement|appartamento|\bunit\b|logement", question, re.I):
                value = f"apartment {value.strip()}"
        if unit == "count" and isinstance(value, (int, float)):
            value = int(round(value))
        elif isinstance(value, float):
            value = round(value, 2)
        if unit not in ("count", "m2", None):
            unit = None
        conf = 0.6 if evidence else 0.45
        missing = [] if evidence else ["the query did not report which rooms it used"]
        echo = _echo(question, value)
        if isinstance(value, str) and not echo and not _in_tables(value, tables):
            conf = min(conf, 0.15)  # e.g. "floor finish of the Bagno" -> "tile": typed by the model, in no table
            missing.append(f"the answer {value!r} does not occur in the drawing's tables (typed by the model)")
            trace.append("guard: text answer not found in any table -> confidence <= 0.15")
        if (sub := _substitute_kind(question, res.get("code", ""))) is not None:
            conf = min(conf, 0.2)  # Q 09:20: "How many escalators ...?" -> code counted kind == 'door' (13 @0.45)
            missing.append(f"the query counted {sub}s, which the question does not ask about; the DXF layers have no "
                           "class for the asked object")
            trace.append(f"guard: the code filters kind '{sub}', a class the question never names -> confidence <= 0.2")
        if echo:
            conf = min(conf, 0.15)  # Q red team: "fire rating of the entrance door of apartment A" -> "apartment A"
            missing.append(f"the answer {value!r} only repeats {echo} named in the question; the tables do not hold "
                           "what was asked")
            trace.append(f"guard: answer repeats {echo} from the question -> confidence <= 0.15")
        return Answer(value=value, unit=unit, confidence=conf, evidence=evidence, trace=trace,
                      solver=self.name, assumptions=["the model wrote the query; every number comes from the DXF tables"],
                      missing=missing)


@register("pdf_vector")
class PdfVectorSolver(DxfSolver):
    """Same rules as `dxf`, but the floor model comes from the PDF's vector + text layer alone (pdffloor.py):
    rooms, areas (printed scale), labels, apartments, doors. Windows/fixtures -> value None + missing."""

    sources = ()

    def can_handle(self, path: str, question: str) -> bool:
        return Path(path).suffix.lower() == ".pdf" and source_of(path) not in ("ifc_models", "opening_design")

    def _load(self, path: str):
        from stoa.solvers.vector.pdffloor import load_pdf_floor

        pdf_rel = path if path.lower().endswith(".pdf") else siblings(path).get(".pdf")
        if not pdf_rel:
            return None, "no PDF", None
        fm, tf, note = load_pdf_floor(str(abspath(pdf_rel)))
        if fm is None:
            return None, note, None
        return fm, pdf_rel, tf
