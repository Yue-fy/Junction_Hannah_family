"""Per-room / relational questions on a CubiCasa-style raster plan, answered from the room graph (no twin, no IFC).

    from experiments.r1.room_graph.answer import solve
    ans = solve("data/cubicasa5k/high_quality-3638.png", "From which room is the balcony accessed?")
    -> stoa.contract.Answer(value='bedroom (H)', evidence=[room box, door box, ...], confidence, trace, assumptions)

Pipeline: room_graph(path, printed=True) (CC5K segmentation + icons, printed areas: one cached VLM call) ->
graph_text -> ONE local 8B call as a text model (JSON: value, unit, rooms, terms) -> sums are computed here from
`terms` (the LLM only picks the numbers; 12.5 + 12.0 was '24.0' when the LLM added) -> evidence = the boxes of the
rooms it used plus the windows / doors / fixtures in them that the question is about.
Measured on by-eye probes (research/methods.md 8i). Pretrained CubiCasa5K weights -> D8: cc5k=1 path only.
Confidence is a provisional rule (n = 43 probe questions), NOT calibrated: printed areas 0.85 (0.6 when printed
without a unit); relations / counts 0.7; estimated areas 0.4; a 'merged' region 0.5.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.r1.room_graph.graph import graph_text, room_graph  # noqa: E402

SYSTEM = ("You answer questions about one apartment floor plan from its room graph. Room names on Finnish plans: "
          "MH/AH/H = bedroom, OH = living room, K/KT/KK/KEITTIÖ = kitchen, KPH/KH/PH/PESUH = bathroom/washroom, "
          "S/L.H./SAUNA = sauna, WC = toilet room, ET/ETEINEN = entrance hall, VH/HV/VAR = closet/storage, "
          "PARV/PARVEKE = balcony, TK = vestibule, RT = dining, SUIHKU = shower room, KHH = utility room. "
          "Reply with JSON only: {\"value\": <a number, or a short text answer that names rooms by their type plus "
          "the label quoted in the graph if the room has one, e.g. \"bathroom\" or \"bedroom (MH 12.0)\"; never "
          "invent a code that is not quoted in the graph; never use an id like R3>, \"unit\": <\"count\"|\"m2\"|null>, "
          "\"rooms\": [<ids of the rooms the answer is about>], \"terms\": [<if the answer is a sum or total of "
          "areas or counts: the numbers to add, one per room; else []>], \"why\": <one short sentence>}.")

GRAPH_NOTE = ("The room graph below was extracted automatically from the plan image (CubiCasa5K segmentation). "
              "'doors to' lists the rooms a door connects (an apartment's hall may be split into an 'entry' room and "
              "parts of other rooms); the quoted text is the label printed in that room.")

_ICON_WORDS = {"window": r"window|ikkun|fenster|fenêtre|finestr", "door": r"door|ovi|ove|tür|porte|port",
               "toilet": r"toilet|wc|seat|istuin", "sink": r"sink|basin|allas", "bathtub": r"bath ?tub|amme",
               "sauna_bench": r"sauna"}


def _evidence(path: str, g: dict, ids: list[str], question: str, items_only: bool = False) -> list:
    """Boxes of the rooms used + the windows / doors / fixtures in them that the question names.  items_only (a count
    of windows / doors / fixtures): leave the room's own box out, so the located items ARE the counted objects (the
    eval's 'located items = answer' check, W5's card); each item's note names its room."""
    from stoa.contract import Evidence
    by = {r["id"]: r for r in g["rooms"]}
    q = question.lower()
    ev = []
    for rid in ids:
        r = by.get(rid)
        if not r:
            continue
        note = f"{r['cls']}" + (f" '{r['label']}'" if r.get("label") else "")
        if r.get("printed"):
            note += " printed " + " + ".join(f"{p['m2']} m²" for p in r["printed"])
        if not items_only:
            ev.append(Evidence(file=path, bbox=[float(v) for v in r["bbox"]], bbox_space="image_px", note=note))
        if re.search(_ICON_WORDS["window"], q):
            for k, b in enumerate(r["windows"], 1):
                ev.append(Evidence(file=path, bbox=[float(v) for v in b], bbox_space="image_px",
                                   note=f"window {k} of {note.split(' printed')[0]}"))
        if re.search(_ICON_WORDS["door"], q) or re.search(r"enter|access|reach|from which|through|opens? onto", q):
            doors = {d["id"]: d for d in g["doors"]}
            for did in r["doors"]:
                d = doors.get(did)
                if d:
                    ev.append(Evidence(file=path, bbox=[float(v) for v in d["box"]], bbox_space="image_px",
                                       note=f"door {did} between {' and '.join(d['between'])}"))
        for name in ("toilet", "sink", "bathtub", "sauna_bench"):
            if re.search(_ICON_WORDS[name], q):
                for b in r["fixtures"].get(name, []):
                    ev.append(Evidence(file=path, bbox=[float(v) for v in b], bbox_space="image_px",
                                       note=f"{name} in {note.split(' printed')[0]}"))
    seen, out = set(), []
    for e in ev:  # a door between two used rooms appears twice
        k = (tuple(e.bbox), e.note.split(" between")[0][:12])
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def solve(path: str, question: str, backend: str = "local", textlayer: bool | None = None):
    """textlayer: labels + printed areas from W3's OCR text layer (None -> env R1_RG_TEXTLAYER, default off)."""
    import os
    from stoa import llm
    from stoa.contract import Answer
    if textlayer is None:
        textlayer = os.environ.get("R1_RG_TEXTLAYER", "0") == "1"
    g = room_graph(path, printed=True, textlayer=textlayer)
    if not g:
        return Answer(value=None, solver="room_graph", confidence=0.0,
                      missing=["no room segmentation for this plan (CC5K map not cached and live run unavailable)"])
    text = graph_text(g)
    res = llm.chat(GRAPH_NOTE + "\n\n" + text + "\n\nQuestion: " + question, system=SYSTEM, backend=backend,
                   max_tokens=250, cache=True)
    try:
        js = llm.extract_json(res.text) or {}
        if isinstance(js, list):
            js = js[0] if js and isinstance(js[0], dict) else {}
    except Exception:  # noqa: BLE001
        js = {}
    value, unit = js.get("value"), js.get("unit")
    ids = [str(i) for i in (js.get("rooms") or []) if re.fullmatch(r"R\d+", str(i))]
    terms = []
    for t in js.get("terms") or []:
        try:
            terms.append(float(str(t).replace(",", ".")))
        except ValueError:
            pass
    trace = [f"room graph: {len(g['rooms'])} rooms, {len(g['doors'])} doors, {len(g['windows'])} windows "
             f"(CubiCasa5K segmentation, CC BY-NC 4.0)", f"llm: {str(js.get('why') or res.text)[:200]}"]
    if len(terms) >= 2 and unit in ("m2", "count"):
        # The LLM picks the numbers, Python adds them -- but only to fix an arithmetic slip (its value within 10% of
        # the sum: 12.5 + 12.0 -> '24.0'). A larger gap means it answered from another basis (e.g. a printed
        # apartment total 53.0 while listing room terms summing to 63.5): keep its value, note the gap.
        s = round(sum(terms), 2)
        try:
            v = float(str(value).replace(",", ".").split()[0])
        except (ValueError, IndexError):
            v = None
        if v is not None and s > 0 and abs(v - s) <= 0.10 * s:
            trace.append(f"sum computed: {' + '.join(f'{t:g}' for t in terms)} = {s:g} (LLM said {value})")
            value = int(s) if unit == "count" and float(s).is_integer() else s
        else:
            trace.append(f"LLM value {value} kept; its listed terms sum to {s:g}")
    by = {r["id"]: r for r in g["rooms"]}
    used = [by[i] for i in ids if i in by]
    if isinstance(value, str):  # internal ids never reach the user: '(R9)' -> the room's printed label, or nothing
        def _name(m):
            r = by.get(m.group(1))
            return f" ({r['label']})" if r and r.get("label") else ""
        value = re.sub(r"\s*\((R\d+)\)", _name, value)
        value = re.sub(r"\s*\((?:R\d+(?:,\s*)?)+\)", "", value).strip() or value
    assumptions, missing = [], []
    conf = 0.7
    if unit == "m2":
        if used and all(r.get("printed") for r in used):
            unitless = any(p.get("unitless") for r in used for p in r["printed"])
            conf = 0.6 if unitless else 0.85
            assumptions.append("areas as printed on the plan" + (" (numbers printed without a unit, read as m²)"
                                                                  if unitless else ""))
        else:
            conf = 0.4
            assumptions.append("no printed area for some rooms: estimated from door widths (80% band on the card)")
            missing.append("printed room areas or a scale")
    if any(r.get("merged") for r in used):
        conf = min(conf, 0.5)
        missing.append("two rooms share one segmented region (a thin partition was missed)")
    if not used:
        conf = min(conf, 0.5)
        missing.append("the answer could not be tied to a segmented room")
    if value is None:
        conf = 0.0
    q = question.lower()
    items_only = unit == "count" and any(re.search(_ICON_WORDS[k], q) for k in ("window", "door", "toilet", "sink",
                                                                                   "bathtub")) \
        and not re.search(r"how\s+many\s+(?:rooms?|spaces?|bedrooms?)\b", q)
    ev = _evidence(path, g, ids, question, items_only=items_only)
    if items_only and not ev:  # nothing located: show the rooms instead
        ev = _evidence(path, g, ids, question)
    return Answer(value=value, unit=unit if unit in ("m2", "count") else None, confidence=conf,
                  evidence=ev, trace=trace, solver="room_graph",
                  assumptions=assumptions, missing=missing)


if __name__ == "__main__":
    a = solve(sys.argv[1], " ".join(sys.argv[2:]))
    print(a.model_dump_json(indent=1))
