"""Text-grounded answers on raster drawings without a template (historical scans, unseen plan styles).

One VLM call gets the image AND the drawing's text layer (textlayer.py: every printed line with its position, read
tile by tile at ~2x, so small title-block print is legible), and must say which text lines its answer comes from.
Those lines' boxes become the Evidence (image_px), so a reader can check the answer in seconds. Without such a line
the answer is an image-only reading at low confidence, said so in `missing`.

Numbers: a printed scale note / dimension string / area is parsed deterministically (textlayer.scales, dimensions,
areas) and given to the model as facts; it states its assumptions (e.g. "no scale printed").
"""

from __future__ import annotations

import json
import re

from stoa import llm
from stoa.contract import Answer, Evidence
from stoa.solvers.raster import scalebar as SB
from stoa.solvers.raster import textlayer as T

# a size question (length / width / height / area / distance) in the languages of the dataset
_SIZE = re.compile(r"\b(length|long|width|wide|height|high|tall|area|size|dimensions?|distance|span|depth|deep|"
                   r"perimeter|how big|square (?:feet|foot|meters?|metres?)|sq\.? ?ft|m²|m2|ft²|pituus|pitkä|leveys|"
                   r"korkeus|pinta-ala|länge|lang|breite|breit|höhe|hoch|fläche|longueur|largeur|hauteur|surface|"
                   r"superficie|lunghezza|larghezza|altezza|längd|lång|bredd|höjd|yta)\b", re.I)

MEASURE = (', "measure": {"bbox_2d": [x1, y1, x2, y2], "extent": "width|height|area"} (ONLY if no printed text '
           'gives the size: the box of the element whose size is asked, 0-1000 relative to the image, and which '
           'extent the question asks for; the program measures it with the graphic scale bar)')

PROMPT ="""You answer a question about a scanned technical drawing (architecture / engineering).
You get the image and the list of texts read from it: [id] (x%, y%) text, where x% and y% are the position of the
text's centre as a percentage of the image width and height.
Use the texts for anything printed (names, places, numbers, dimensions, scale notes, dates, sheet numbers); use the
image for the layout, the drawing type and anything drawn but not written.
{facts}
TEXTS:
{texts}

QUESTION: {question}

Reply with JSON only: {{"answer": "<short final answer: a name, a number, a short phrase, yes/no>", "unit": "<unit of a
numeric answer (m, m2, ft, ft2, count, ...) or empty>", "lines": [<ids of the text lines the answer is read from;
[] if it comes only from the image>], "assumptions": "<what you assumed, or empty>"{measure}}}"""

SCHEMA = {"type": "object", "properties": {
    "answer": {"type": "string", "maxLength": 200},
    "unit": {"type": "string", "maxLength": 12},
    "lines": {"type": "array", "items": {"type": "integer"}, "maxItems": 8},
    "assumptions": {"type": "string", "maxLength": 300}},
    "required": ["answer", "unit", "lines", "assumptions"]}
SCHEMA_MEASURE = {**SCHEMA, "properties": {**SCHEMA["properties"], "measure": {
    "type": "object", "properties": {
        "bbox_2d": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
        "extent": {"type": "string", "enum": ["width", "height", "area"]}}, "required": ["bbox_2d", "extent"]}}}

_NUM = re.compile(r"^\s*-?\d+(?:[.,]\d+)?\s*$")


def facts(tl: T.TextLayer, bars: list | None = None) -> str:
    out = []
    sc = T.scales(tl)
    if sc:
        out.append("Scale notes found: " + "; ".join(f"'{s['line'][:50]}' = 1:{s['ratio']:g}" for s in sc[:3]) + ".")
    else:
        out.append("No scale note was found in the texts.")
    ar = T.areas(tl)
    if ar:
        out.append(f"Printed areas: {len(ar)} (e.g. " + ", ".join(a["line"][:30] for a in ar[:4]) + ").")
    for b in (bars or [])[:2]:
        out.append(f"Graphic scale bar found ({b.unit}): the program can measure a drawn element with it.")
    return "\n".join(out)


def answer(path: str, question: str, image_path: str | None = None, backend: str = "local",
           max_texts: int = 160, solver: str = "raster") -> Answer:
    img_path = image_path or path
    tl = T.text_layer(img_path)
    W, H = tl.size
    items = tl.items[:max_texts]
    texts = "\n".join(f"[{k}] ({100 * i.cx / W:.0f}%, {100 * i.cy / H:.0f}%) {i.text[:100]}" for k, i in enumerate(items))
    bars = []
    if _SIZE.search(question):  # a size question: a graphic scale bar lets the PROGRAM measure (scalebar.py)
        try:
            bars = [b for b in SB.bars(img_path, backend=backend, layer=tl) if b.unit in SB.UNIT_M]
        except Exception:  # noqa: BLE001 - a bar is a bonus, never a reason to fail the question
            bars = []
    if bars and _AREA_Q.search(question):
        got = _room_area_answer(img_path, question, tl, bars, solver)
        if got is not None:
            return got
    prompt = PROMPT.format(facts=facts(tl, bars), texts=texts or "(no text found)", question=question.strip(),
                           measure=MEASURE if bars else "")
    r = llm.chat(prompt, images=[str(T._abspath(img_path))], backend=backend, max_tokens=300,
                 json_schema=SCHEMA_MEASURE if bars else SCHEMA, cache=True)
    trace = [f"text layer: {len(tl.items)} texts in {tl.tiles} tile(s); {facts(tl).splitlines()[0]}"]
    if bars:
        trace.append(bars[0].describe() + (f" [{'; '.join(bars[0].notes)}]" if bars[0].notes else ""))
    try:
        d = json.loads(r.text)
    except ValueError:
        m = re.search(r"\{.*\}", r.text, re.S)
        d = json.loads(m.group()) if m else {}
    val = str(d.get("answer", "")).strip()
    if not val:
        return Answer(value=None, solver=solver, trace=trace + ["no answer from the text-grounded reading"],
                      missing=["the drawing's text did not answer the question"])
    cited = [items[k] for k in d.get("lines", []) if isinstance(k, int) and 0 <= k < len(items)]
    # does the answer literally appear in the cited lines (or anywhere in the text layer)?
    in_cited = any(T.match_score(val, i.text) >= 0.85 for i in cited) or \
        (len(val) > 2 and T.match_score(val, " ".join(i.text for i in cited)) >= 0.85)
    unit = str(d.get("unit", "")).strip() or None
    value: object = val
    if _NUM.match(val):
        v = float(val.replace(",", "."))
        value = int(v) if v.is_integer() and (unit in (None, "count")) else v
    else:
        fm = T._FTIN.fullmatch(val.strip().rstrip('"”').strip() + '"') or T._FTIN.fullmatch(val.strip())
        if fm:  # a dimension string 187'-0" -> 187.0 ft (the printed text stays in the trace and evidence)
            value, unit = round(int(fm.group(1)) + (T._frac(fm.group(2)) / 12 if fm.group(2) else 0), 3), "ft"
    ev = [Evidence(file=img_path, page=0, bbox=[round(x, 1) for x in i.box], bbox_space="image_px",
                   note=f"text '{i.text[:60]}'") for i in cited[:6]]
    printed = any(re.search(r"\d", i.text) for i in cited)
    if bars and not printed and isinstance(d.get("measure"), dict):
        got = measure(d["measure"], bars[0], question, tl.size)
        if got is not None:
            mv, mu, mbox, note = got
            trace.append(f"the VLM's own reading was '{val}'; {note}")
            return Answer(value=mv, unit=mu, confidence=MEASURED_CONF, solver=solver, trace=trace,
                          evidence=[Evidence(file=img_path, page=0, bbox=mbox, bbox_space="image_px",
                                             note="measured element (bounding box)")] + bars[0].evidence(img_path),
                          assumptions=[f"measured on the drawing: the element's bounding box × the graphic scale bar "
                                       f"({bars[0].px_per_unit:.2f} px per {bars[0].unit}); no printed dimension "
                                       "gives this size"]
                          + (["area = box width × height (a rectangle)"] if d["measure"].get("extent") == "area"
                             else []),
                          missing=["a printed dimension or the element's exact outline (a box measurement is an "
                                   "estimate)"])
    # Confidence from the 80-question scan probe (artifacts/W3/scan_text.jsonl, run 031842-346a; HABS + Finna, judged):
    # cited lines 54/72 right (75%; HABS alone 90%), image-only 1/2 -> cited 0.75, image-only 0.3
    conf = 0.75 if cited else 0.3
    missing = [] if cited else ["the answer is not printed as text: an image-only reading"]
    if isinstance(value, (int, float)) and any(abs(float(n) - value) < 1e-9 for n in
                                               re.findall(r"\d+(?:\.\d+)?", question)) and _SIZE.search(question):
        # the 'size' is a number the question itself names (room 0.20 -> '0.20 m²'): an echo, not a reading
        conf = 0.05
        missing = [*missing, "the answer repeats a number from the question (likely the room's number, not its size)"]
    assumptions = [a for a in [str(d.get("assumptions", "")).strip()] if a and a.lower() not in ("none", "n/a")]
    trace.append(f"answer '{val}' from text lines {[k for k in d.get('lines', [])][:8]}"
                 + (" (literal match)" if in_cited else ""))
    return Answer(value=value, unit=unit, confidence=conf, evidence=ev, solver=solver, trace=trace,
                  assumptions=assumptions, missing=missing)


# VLM-box measurements: Swiss PNG rooms (experiments/w3/measure_eval.py, 22 Qs) 0 within 2%, 5 within 20%, median
# error 47%: an estimate whose box a reader can check, not a measurement
MEASURED_CONF = 0.05
_AREA_Q = re.compile(r"\b(area|floor space|square (?:feet|foot|meters?|metres?)|sq\.? ?ft|m²|m2|ft²|pinta-ala|fläche|"
                     r"flache|surface|superficie|yta|area)\b", re.I)


def _room_area_answer(img_path: str, question: str, tl: T.TextLayer, bars: list, solver: str):
    """'Area of room 2.32 / «Bagno»': the label in the text layer -> a printed area next to it (read), else the room's
    flood-filled outline x the scale bar (measure.py). No VLM call. None when the room or a metric bar is missing."""
    from stoa.solvers.raster import measure as M

    lab = M.find_label(tl, question)
    bar = next((b for b in bars if b.px_per_m), None)
    if lab is None or bar is None:
        return None
    h = lab.box[3] - lab.box[1]

    def d2(a, it):
        return ((a["box"][0] + a["box"][2]) / 2 - it.cx) ** 2 + ((a["box"][1] + a["box"][3]) / 2 - it.cy) ** 2

    # a printed area belongs to the room whose number label is NEAREST to it (Swiss renders print 'NN.NN m²' under
    # the number; a neighbour's area can be as close vertically)
    ids = [i for i in tl.items if M._ROOM_ID.fullmatch(i.text.strip())] or [lab]
    near = [a for a in T.areas(tl) if d2(a, lab) < (6 * h) ** 2 and min(ids, key=lambda i: d2(a, i)) is lab]
    lab_ev = Evidence(file=img_path, page=0, bbox=[round(x, 1) for x in lab.box], bbox_space="image_px",
                      note=f"room label '{lab.text}'")
    if near:
        a = min(near, key=lambda a: d2(a, lab))
        return Answer(value=a["value"], unit=a["unit"], confidence=0.75, solver=solver,
                      evidence=[lab_ev, Evidence(file=img_path, page=0, bbox=[round(x, 1) for x in a["box"]],
                                                 bbox_space="image_px", note=f"printed area '{a['line'][:40]}'")],
                      trace=[f"room label '{lab.text}' at {lab.box}; printed area next to it: '{a['line']}'"])
    r = M.room_area(img_path, lab.box, bar.px_per_m, **M.FILL,
                    others=[i.box for i in ids if i is not lab and M._ROOM_ID.fullmatch(i.text.strip())])
    if r is None or r["wall_frac"] < 0.05 or r["m2"] > 120:
        # not bounded by drawn walls (thin-line historical plans leak: HABS ut0011 'KITCHEN' filled ~100 m², 0% of its
        # outline on walls; Swiss rooms: min 0.01, 5/71 below 0.2) or larger than any single room: no measurement
        return None
    unit = "ft2" if re.search(r"\b(sq\.? ?ft|square feet|ft²|feet)\b", question, re.I) else "m2"
    v = r["m2"] / 0.3048 ** 2 if unit == "ft2" else r["m2"]
    W = M.WITHIN
    return Answer(value=round(v, 2), unit=unit, confidence=round(W["2%"], 2), solver=solver,
                  evidence=[lab_ev, Evidence(file=img_path, page=0, bbox=r["box"], bbox_space="image_px",
                                             note=f"room outline (flood fill): {r['m2']:.2f} m²")]
                  + bar.evidence(img_path),
                  trace=[f"room label '{lab.text}' at {[round(x) for x in lab.box]}", bar.describe(), *r["notes"]],
                  assumptions=[f"the room's outline is the blank region around its label up to the drawn walls "
                               f"(convex hull, so fixtures against walls count), measured with the graphic scale bar "
                               f"({bar.px_per_m:.2f} px per m); no area is printed for this room"],
                  missing=[f"a printed area or dimensions: on 71 Swiss plan rooms this measurement was within 2% for "
                           f"{100 * W['2%']:.0f}%, within 5% for {100 * W['5%']:.0f}% and within 10% for "
                           f"{100 * W['10%']:.0f}%"])


def measure(m: dict, bar, question: str, size: tuple[int, int]):
    """A VLM box (0-1000 relative) of the element + the scale bar -> (value, unit, box_px, trace note), or None.
    The unit follows the question (m vs ft) when it names one, else the bar's."""
    try:
        x1, y1, x2, y2 = (float(v) for v in m["bbox_2d"])
    except (KeyError, TypeError, ValueError):
        return None
    W, H = size
    box = [round(min(x1, x2) / 1000 * W, 1), round(min(y1, y2) / 1000 * H, 1), round(max(x1, x2) / 1000 * W, 1),
           round(max(y1, y2) / 1000 * H, 1)]
    wpx, hpx = box[2] - box[0], box[3] - box[1]
    if wpx < 3 or hpx < 3 or not bar.px_per_m:
        return None
    ext = m.get("extent", "width")
    q = question.lower()
    unit = "ft" if re.search(r"\b(feet|foot|ft|sq\.? ?ft|ft²)\b", q) else \
        "m" if re.search(r"\b(meters?|metres?|m|m²|m2|mètres?|metri|metros?|meter)\b", q) else bar.unit
    per = bar.px_per_m * SB.UNIT_M.get(unit, 1.0)  # px per unit of the answer
    if ext == "area":
        v, u = (wpx / per) * (hpx / per), ("m2" if unit == "m" else f"{unit}2")
    else:
        v, u = (wpx if ext == "width" else hpx) / per, unit
    return round(v, 2), u, box, f"measured {ext}: box {wpx:.0f} x {hpx:.0f} px at {per:.2f} px per {unit} = {v:.2f} {u}"
