"""Free-text IFC questions (IFC-Bench style) answered by a small LLM over a compact, deterministic FACT CARD.

The card is built from the cached index only (no file re-parse): project, storeys (elevation, element counts),
class totals, type names with counts, external/load-bearing splits, fire ratings and materials (when indexed),
rooms with net floor areas. The LLM is told to use only these facts, so its numbers are traceable to the model;
the card is put in the trace (truncated) and the elements of the asked kind are the evidence.

Cost: one local-server call (~2-4k tokens in), metered by stoa.llm through record_cost.
"""

from __future__ import annotations

import collections

from stoa.solvers.ifc.index import IfcIndex
from stoa.solvers.ifc.parse import KIND_CLASSES, Intent

MAIN = ["IfcWall", "IfcWallStandardCase", "IfcCurtainWall", "IfcSlab", "IfcRoof", "IfcColumn", "IfcBeam", "IfcDoor",
        "IfcWindow", "IfcStair", "IfcStairFlight", "IfcRamp", "IfcRailing", "IfcCovering", "IfcSpace", "IfcFooting",
        "IfcPile", "IfcPlate", "IfcMember", "IfcFurnishingElement", "IfcSanitaryTerminal", "IfcLightFixture"]

SYSTEM = ("You answer questions about one building information model (IFC). Use ONLY the facts given, which "
          "were extracted from the model by a program. Quote numbers with units. If the facts do not contain the "
          "answer, say exactly which information is missing from the model and, if reasonable, give a clearly "
          "labelled estimate. Answer in at most 12 short lines.")


def placeholder_spaces(idx: IfcIndex) -> bool:
    """True when the IfcSpaces are placeholders (>= 80% of >= 5 spaces have a footprint <= 1.01 m², e.g. the
    sixty5 ArchiCAD zones: 1 m² in geometry AND in every quantity set). Their areas say nothing about the rooms."""
    sp = [e for e in idx.elements.values() if e.cls == "IfcSpace"]
    tiny = [e for e in sp if e.geo and e.geo.footprint_area is not None and e.geo.footprint_area <= 1.01]
    return len(sp) >= 5 and len(tiny) >= 0.8 * len(sp)


PLACEHOLDER_NOTE = ("WARNING: the IfcSpaces in this model are placeholders (about 1 m² each in geometry and quantity "
                    "sets); the model has no real room areas. Say so, and do not present 1 m² as a room area.")


def storey_card(idx: IfcIndex, storey) -> list[str]:
    """Everything on one storey (the one the question names): class counts, types per class, rooms."""
    els = [e for e in idx.elements.values() if e.storey == storey.guid]
    L = [f"FOCUS STOREY '{storey.name}' (elevation {storey.elevation} m): {len(els)} elements: "
         + ", ".join(f"{c} {n}" for c, n in collections.Counter(e.eff_cls for e in els).most_common(14))]
    for c, _ in collections.Counter(e.eff_cls for e in els if e.eff_cls != "IfcOpeningElement").most_common(8):
        types = collections.Counter(e.type_name or e.object_type or "(untyped)" for e in els if e.eff_cls == c)
        L.append(f"  on '{storey.name}' {c} types: " + "; ".join(f"{t} x{n}" for t, n in types.most_common(8)))
    rs = [e for e in els if e.cls == "IfcSpace"]
    if rs and placeholder_spaces(idx):
        L.append("  " + PLACEHOLDER_NOTE)
    if rs:
        L.append(f"  rooms on '{storey.name}' (long name (number) - net floor area m², gross m² when given):")
        for e in sorted(rs, key=lambda e: e.name or "")[:40]:
            ga = next((v for k, v in e.qto.items() if k.endswith("GrossFloorArea")), None)
            L.append(f"   - {e.long_name or ''} ({e.name or ''}) {(e.geo.footprint_area or 0) if e.geo else 0:.1f}"
                     + (f", gross {ga:.1f}" if ga else ""))
    else:
        L.append(f"  no IfcSpace on '{storey.name}'")
    return L


def fact_card(idx: IfcIndex, it: Intent | None = None, max_lines: int = 160, storey=None) -> str:
    els = list(idx.elements.values())
    L = [f"Model: {idx.path.split('/')[-1]} | schema {idx.schema} | project '{idx.project_name or ''}'"
         + (f" | buildings {', '.join(b for b in idx.building_names if b)}" if any(idx.building_names) else "")]
    app = getattr(idx, "application", None)
    if app:
        L.append(f"Authoring application: {app}")
    tot = collections.Counter(e.eff_cls for e in els)
    L.append("Element totals: " + ", ".join(f"{c} {n}" for c, n in tot.most_common(25)))
    L.append("Storeys (elevation m; counts of doors/windows/walls/spaces):")
    for s in idx.storeys:
        on = collections.Counter(e.eff_cls for e in els if e.storey == s.guid)
        walls = on["IfcWall"] + on["IfcWallStandardCase"]
        L.append(f"- {s.name}: {s.elevation if s.elevation is not None else '?'}; doors {on['IfcDoor']}, windows "
                 f"{on['IfcWindow']}, walls {walls}, spaces {on['IfcSpace']}")
    want = list(KIND_CLASSES.get(it.kind, ())) if it is not None and it.kind else []
    # the asked kind first, then the model's own most frequent classes (MEP models), then main building classes
    top = [c for c, _ in tot.most_common(12) if c not in want and c not in ("IfcOpeningElement",)]
    classes = want + top + [c for c in MAIN if c not in want and c not in top and tot.get(c)]
    for c in classes[:18]:
        group = [e for e in els if e.eff_cls == c]
        if not group:
            continue
        types = collections.Counter(e.type_name or e.object_type or "(untyped)" for e in group)
        L.append(f"{c} types: " + "; ".join(f"{t} x{n}" for t, n in types.most_common(8))
                 + (f"; ... {len(types) - 8} more" if len(types) > 8 else ""))
        ext = collections.Counter(next((v for k, v in e.props.items() if k.endswith(".IsExternal")), None)
                                  for e in group)
        if ext.get(True) or ext.get(False):
            L.append(f"  {c} external {ext.get(True, 0)}, internal {ext.get(False, 0)}, unknown {ext.get(None, 0)}")
        lb = sum(1 for e in group if any(k.endswith(".LoadBearing") and v is True for k, v in e.props.items()))
        if lb:
            L.append(f"  {c} load-bearing {lb}")
        fr = collections.Counter(v for e in group for k, v in e.props.items() if k.endswith(".FireRating") and v)
        if fr:
            L.append(f"  {c} fire ratings: " + ", ".join(f"{v} x{n}" for v, n in fr.most_common(6)))
        mats = collections.Counter(m for e in group for m in (getattr(e, "materials", None) or []))
        if mats:
            L.append(f"  {c} materials: " + ", ".join(f"{m} x{n}" for m, n in mats.most_common(6)))
        q = collections.defaultdict(float)
        for e in group:
            for k, v in e.qto.items():
                name = k.split(".", 1)[1]
                if name in ("NetVolume", "Length", "NetSideArea", "NetArea", "Area", "GrossVolume") and \
                        (k.startswith("Qto_") or "BaseQuantities" in k):
                    q[name] += v
        if q:
            L.append(f"  {c} quantity totals: " + ", ".join(f"{k} {v:.2f}" for k, v in q.items()))
    spaces = [e for e in els if e.cls == "IfcSpace"]
    if spaces and placeholder_spaces(idx):
        L.append(PLACEHOLDER_NOTE)
    if spaces:
        L.append("Rooms (IfcSpace: long name (number) - net floor area m² from geometry):")
        by = collections.defaultdict(list)
        for e in spaces:
            by[e.storey].append(e)
        for s in idx.storeys:
            rs = by.get(s.guid, [])
            if not rs:
                continue
            area = sum((e.geo.footprint_area or 0) for e in rs if e.geo)
            L.append(f"- {s.name} ({len(rs)} rooms, {area:.1f} m²): " + "; ".join(
                f"{e.long_name or ''} ({e.name or ''}) {(e.geo.footprint_area or 0) if e.geo else 0:.1f}"
                for e in sorted(rs, key=lambda e: -((e.geo.footprint_area or 0) if e.geo else 0))[:25]))
    L = L[:max_lines]
    if storey is not None:
        L = L[:3] + storey_card(idx, storey) + L[3:]
    return "\n".join(L)


def answer_free_text(idx: IfcIndex, question: str, it: Intent | None, storey=None,
                     extra: str | None = None) -> tuple[str | None, str, dict]:
    """-> (answer text or None, card, info). Uses the shared local model server."""
    from stoa import llm

    card = fact_card(idx, it, storey=storey)
    if extra:
        card = extra + "\n" + card
    try:
        r = llm.chat([{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": f"FACTS:\n{card}\n\nQUESTION: {question}"}],
                     max_tokens=450, temperature=0.0)
    except TypeError:  # older client signature: (prompt, ...)
        r = llm.chat(f"{SYSTEM}\n\nFACTS:\n{card}\n\nQUESTION: {question}", max_tokens=450)
    except Exception as ex:  # noqa: BLE001 - server down etc.: the caller keeps its refusal
        return None, card, {"error": f"{type(ex).__name__}: {ex}"}
    text = (getattr(r, "text", "") or "").strip()
    return (text or None), card, {"latency_s": getattr(r, "latency_s", None)}
