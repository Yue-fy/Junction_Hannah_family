"""Answer questions ABOUT the links (plan sheets <-> IFC model <-> storeys <-> rooms) from stoa.kg, read-only.

Q's red-team v17 (KNOWLEDGE 08:47): the knowledge graph cross-checks answers but never answers "do the plan and the
model agree on the windows of '1.korrus'?", "how many windows are in the model but not drawn?", "which sheet shows the
server room?", "how many floor plan sheets?".  Method = W2's 'point at rows, Python does the arithmetic' (KNOWLEDGE
08:42): the project graph is serialised as numbered fact rows, ONE local text call returns {op, rows, a, b}, Python
computes the value from the cited rows' numbers and returns the rows' boxes/files as evidence.

    from experiments.r1.kg_qa.kgqa import is_link_question, solve
    python experiments/r1/kg_qa/kgqa.py PATH "question"
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stoa.contract import Answer, Cost, Evidence  # noqa: E402

KINDS = {"plan": "floor plan sheet", "section": "section sheet", "elevation": "elevation sheet",
         "raster-plan": "raster plan image", "discipline-model": "other discipline model of the same project",
         "model": "IFC model"}

# A link question names the drawing set / the model-vs-plan relation itself (any of en/de/fi/fr/sv/it/nl/et forms).
_SHEETS = (r"sheets?|drawings?|plans?\b|floor ?plans?|sections?|elevations?|blatt|bl[äa]tter|zeichnung\w*|"
           r"grundriss\w*|schnitt\w*|ansicht\w*|piirustu\w*|pohjapiirustu\w*|leikkau\w*|julkisivu\w*|"
           r"plans? d'?\w*|feuilles?|coupes?|fa[çc]ades?|ritning\w*|planritning\w*|sektion\w*|fasad\w*|"
           r"tavol\w*|piant\w*|sezion\w*|prospett\w*|tekening\w*|plattegrond\w*|doorsnede\w*|joonis\w*|l[õo]ig\w*")
_MODEL = r"\b(ifc|bim|model\w*|maquette|mall\w*|modell\w*|mudel\w*)\b"
_PLAN = (r"\b(plan|floor ?plan|drawing|sheet|grundriss\w*|zeichnung\w*|piirustu\w*|pohja\w*|plan\w*|ritning\w*|"
         r"pianta|tekening|plattegrond|joonis\w*)\b")
_AGREE = (r"\b(agree|match|consistent|same number|differ|discrepan\w*|übereinstimm\w*|stimmen\w*|gleich\w*|"
          r"täsmää\w*|sama\w*|identiques?|même nombre|correspond\w*|överens\w*|stämmer|coincid\w*|"
          r"overeen\w*|ühti\w*|but not|not (drawn|shown)|missing from|nicht (gezeichnet|dargestellt)|"
          r"ei (ole )?piirretty|non (dessiné|représenté)|more \w+ (on|in) .* than the|than the .* (shows|plan)|"
          r"show\w* (every|all)|zeigt (alle|jede)|näyttää kaikki|montre (tous|toutes))\b")
_SHEETN = (r"(floor ?plan |architectural |separate |different )?(sheets?|drawings?|plans?|floor ?plans?|sections?|"
           r"elevations?|grundriss\w*|schnitt\w*|ansicht\w*|bl[äa]tter|blatt|zeichnungen|pohjapiirustu(s|sta|ksia)|"
           r"piirustu(s|sta|ksia)|leikkau\w*|julkisivu\w*|plans?|coupes?|fa[çc]ades?|feuilles?|ritningar|"
           r"planritningar|sektioner|fasader|tavole|piante|sezioni|prospetti|tekeningen|plattegronden|doorsneden|"
           r"gevels|joonised|lõiked|blad|bladet|bladen|blade)")
# 'which sheet/plan/drawing shows X' (the sheet noun right after the question word)
_WHICH_SHEET = (r"\b(which|what|welche[rsm]?|auf welche\w*|in welche\w*|mill\w*|missä|quel(le)?s?|sur quel\w*|vilke[nt]?|"
                r"på vilke\w*|quale|su quale|in quale|welk\w*|op welk\w*|millisel)\s+" + _SHEETN + r"\b")
_COUNT_SHEETS = (r"\b(how many|wie viele|kuinka monta|montako|combien de|combien d'|hur många|quant[ei]|hoeveel|mitu)\s+"
                 + _SHEETN + r"\b")
_NO_PLAN = r"\b(no|without|keine\w*|ohne|ei|ilman|sans|aucun\w*|utan|senza|geen|zonder|pole)\b.{0,30}\b(" + _SHEETS + r")\b"
_OTHER_DATASET = (r"\b(another|other|anderen?|toise\w*|autre|annan|annat|altro|ander|teis\w*|otro)\b.{0,20}"
                  r"\b(dataset\w*|data ?set|datensatz|aineisto\w*|jeu de données|andmebaas\w*|andmekogu\w*|"
                  r"conjunto de datos|insieme di dati|datamängd)")
_ROOM_STOREY = (r"\b((on|in) which|which|what|in welche\w*|auf welche\w*|welche\w*|missä|mill\w*|à quel\w*|"
                r"sur quel\w*|quel\w*|på vilke\w*|vilke\w*|a quale|su quale|in quale|quale|op welk\w*|welk\w*|"
                r"millisel)\s+(floor|storey|story|level|geschoss|stockwerk|etage|ebene|kerroksessa|kerroksella|"
                r"niveau|étage|våning|plan|piano|verdieping|korrusel)\b(?!\s+(area|plan|space|height|finish\w*))")
_NO_ROOMS = r"\b(no|without|keine|ohne|ei|ilman|aucune?|sans|utan|senza|geen)\b.{0,15}\b(rooms?|spaces?|räume?n?|huonei\w*|pièces?|rum|stanze|ruimtes?)\b"


_YESNO = (r"^(do|does|did|is|are|was|were|has|have|can|ist|sind|stimm\w*|hat|haben|gibt|zeigt|onko|ovatko|näkyykö|"
          r"est-ce|le |la |les |y a-t-il|finns|är|stämmer|visar|è|sono|ci sono|is|zijn|klopt|kas|on)\b")
_AGREE_ONLY = (r"\b(agree|match\w*|consistent|same|aligned|übereinstimm\w*|stimmen\w*|täsmää\w*|sama\w*|même|"
               r"identiques?|accord|conformes?|överens|stämmer|coincid\w*|overeen\w*|every|all|alle|kaikki|tous|"
               r"toutes|alla|tutt[ie]|todas|todos|kõik\w*|fully|complete\w*|vollständig\w*|entire\w*)\b")


def _sheet_kinds(question: str) -> set[str]:
    q = question.lower()
    want = set()
    if re.search(r"\b(floor ?plans?|plans?|grundriss\w*|pohjapiirustu\w*|pohj\w*|planritning\w*|piant\w*|"
                 r"plattegrond\w*|plan d'étage|plans d'étage|planer|plannen|planos|plaan\w*)\b", q):
        want.add("plan")
    if re.search(r"\b(sections?|sectional|schnitt\w*|leikkau\w*|coupes?|sektion\w*|snitt\w*|sezion\w*|doorsnede\w*|"
                 r"lõike\w*|secci\w*|corte\w*)\b", q):
        want.add("section")
    if re.search(r"\b(elevations?|ansicht\w*|julkisivu\w*|façades?|facades?|fasad\w*|prospett\w*|gevel\w*|"
                 r"elevaci\w*|alzad\w*)\b", q):
        want.add("elevation")
    if re.search(r"\b(in total|all|altogether|insgesamt|alle|yhteensä|kaikki|au total|tous|totalt|alla|in totale|"
                 r"tutti|totaal|kokku)\b", q) and re.search(r"\b(sheets?|drawings?|blätter|piirustu\w*|feuilles?|"
                                                           r"blad\w*|lehte\w*|lehti|hojas?|fogli|tavole)\b", q):
        want |= {"plan", "section", "elevation"}
    elif want == {"plan", "section", "elevation"}:
        pass  # an enumeration 'plans, sections and elevations' (paraphrases: 'total number of sheets — including …')
    elif "plan" in want and want & {"section", "elevation"}:
        want.discard("plan")  # 'plans de coupe', 'section plans', 'Schnittpläne': the specific kind wins
    return want


# broader, language-general signals (tuned on half A of the LLM paraphrases, tested on half B; 0 dataset fires)
_MODEL2 = r"\b(ifc|bim)\b|\bmodel\w*|\bmodell\w*|\bmalli\w*|\bmodèle\w*|\bmodello\w*|\bmudel\w*|\bmodelo\w*|\bmoodl\w*"
_PLAN2 = (r"\b(plan|plans|planen|plano|planos|floor ?plan\w*|drawing\w*|sheet\w*|zeichnung\w*|grundriss\w*|"
          r"piirustu\w*|piirro\w*|pohjapiirro\w*|dessin\w*|feuillet\w*|disegn\w*|piant\w*|fogli\w*|ritning\w*|"
          r"tekening\w*|plattegrond\w*|joonis\w*|dibujo\w*|blad\w*|lehe\w*|plaan\w*|vloerpl\w*|korrusplaan\w*)\b")
_SET = (r"(drawing ?set|set of (drawings|sheets|plans)|plan ?set|sheet ?set|zeichnungs(satz|set|reihe)\w*|plansatz|"
        r"piirustus(joukko|sarja)\w*|ensemble (des|de) (plans|dessins)|jeu de plans|(insieme|set) (dei|di) disegni|"
        r"ritnings?uppsättning\w*|teckningsuppsättning\w*|tekenreeks|tekeningen ?set|set tekeningen|"
        r"joonis\w* (komplekt|üksus)\w*|conjunto de (dibujos|planos))")
_SHEET3 = (r"\b(which|what|welche[rsm]?|quel(le)?s?|quale|vilke[nt]?|welke|mikä|mill\w*|mis|qué|en qué|cuál)\s+"
           r"(zeichnung|feuillet|foglio|ritning|tekening|hoja|plano|paperi|lehe\w*|blad|sheet|drawing|plan)\b")
_STOREYS = (r"\b(storeys|stories|floors|levels|stockwerke|geschosse|ebenen|kerrokset|kerrat|kerroksi\w*|niveaux|étages|"
            r"piani|livelli|våningar|plan|verdiepingen|korruseid|korrused|plantas|pisos|niveles)\b")
_NEG = (r"\b(no|zero|without|devoid|none|keine\w*|ohne|ei|eivät|yhtään|aucune?|sans|nessun\w*|non|inga|utan|geen|"
        r"ühtegi|pole|ningun\w*|sin)\b")
_ROOMW = (r"(\brooms?\b|\bspaces?\b|räume|\braum|huone|\bpièces?|\bespaces?|\bstanze|\bspazi|\brum\b|kamers|ruimtes|"
          r"ruumi|habitaci\w*|espacios)")


def is_link_question(question: str) -> dict:
    """{fire, why}: the question asks about the drawing set or the plan<->model relation (not about the building
    alone).  Deliberately narrow: 'how many doors on 1.korrus' (a building fact) does NOT fire."""
    q = question.lower()
    why = []
    if re.search(_MODEL, q) and re.search(_PLAN, q) and re.search(_AGREE, q):
        why.append("plan vs model")
    if re.search(r"\b(is there|are there|gibt es|existiert|onko|ovatko|y a-t-il|existe-t-il|finns det|c'è|ci sono|"
                 r"is er|zijn er|kas on)\s+(a |an |any |ein\w* |une? |des |jokin |mitään |någon |några |un[ao]? |een |mingi )?"
                 + _SHEETN + r"\b", q):
        why.append("sheet exists")
    if re.search(_COUNT_SHEETS, q):
        why.append("count sheets")
    if re.search(_WHICH_SHEET, q):
        why.append("which sheet")
    if re.search(_NO_PLAN, q) and re.search(r"\b(storeys?|stor(y|ies)|floors?|levels?|geschoss\w*|kerro\w*|"
                                            r"niveaux?|étages?|våning\w*|piani|verdieping\w*|korrus\w*)\b", q):
        why.append("storeys without a plan")
    if re.search(_NO_ROOMS, q) and re.search(r"\b(storeys?|stor(y|ies)|floors?|levels?|geschoss\w*|kerro\w*|niveaux?|"
                                             r"étages?)\b", q):
        why.append("storeys without rooms")
    if re.search(_OTHER_DATASET, q):
        why.append("same building elsewhere")
    if re.search(_ROOM_STOREY, q) and not re.search(r"\b(more|fewer|less|most|least|largest|smallest|highest|lowest|"
                                                     r"biggest|tiniest|größte\w*|kleinste\w*|suurin\w*|pienin\w*|"
                                                     r"plus grande?s?|plus petite?s?|största|minsta|più grande|"
                                                     r"più piccol\w*|grootste|kleinste|más grande|más pequeñ\w*|"
                                                     r"suurim\w*|väikseim\w*|"
                                                     r"mehr|weniger|meisten|enemmän|vähemmän|eniten|plus de|moins de|"
                                                     r"flest|fler|più|meno|meer|minder|rohkem)\b", q) and (re.search(r"['\"‘’“”]", q) or re.search(
            r"(\broom|raum\b|huone|\bpièce|\bsalle|\blocal|rum(met)?\b|\bstanza|ruimte\b|ruum\b)", q)):
        why.append("room -> storey/sheet")
    if not why and re.search(_MODEL2, q) and re.search(_PLAN2, q):
        why.append("plan and model named")
    if not why and re.search(_MODEL, q) and re.search(
            r"\b(than|as|als|kuin|que|än|di|dan)\s+(are|is|were|sind|on|sont|är|sono|zijn|son)?\s*(drawn|shown|"
            r"gezeichnet|dargestellt|piirretty|näytetty|dessinée?s?|représentée?s?|ritade?|visade?|disegnat\w*|"
            r"getekend|dibujad\w*)\b", q):
        # r1v5 'Has the BIM model got more windows on this level than are drawn here?' (no sheet noun)
        why.append("model vs drawn")
    if not why and re.search(r"^(is there|are there|gibt es|onko|löytyykö|y a-t-il|finns det|c'è|is er|hay|kas on)\s+"
                             r"(an? |any |the |ein\w* |une? |ett? |un[ao]? |een )?(3d[- ]?model\w*|ifc|bim model|"
                             r"bim file|dxf|dwg|cad file|building model)\b", q):
        # the FILE is what is asked about ('Is there a 3D model or IFC file for this apartment?'), not its contents
        # ('Are there any fire extinguishers in the BIM model?' must not fire)
        why.append("model exists")
    if not why and re.search(_SET, q):
        why.append("drawing set")
    if not why and re.search(_SHEET3, q) and not re.search(r"\b(scale|maßstab|mittakaava|échelle|scala|skala|schaal|"
                                                          r"escala|mõõtkava)\b", q):
        why.append("which sheet")
    if not why and re.search(_STOREYS, q) and re.search(_NEG, q) and re.search(_ROOMW, q):
        why.append("storeys without rooms")
    return {"fire": bool(why), "why": ", ".join(why)}


def _short(p: str | None) -> str:
    return Path(p).stem.split("_")[-1] if p else "-"


def facts(path: str) -> tuple[list[dict], dict]:
    """Numbered fact rows for the whole project behind `path` (ifc_models / ifc_bench), from stoa.kg."""
    from stoa.kg import links, project_graph

    g = project_graph(path) or {}
    if not g:
        return [], {}
    this_plan = path if path.endswith(".pdf") else None
    this_extra = None
    if this_plan and g.get("model") and not any(f["path"] == this_plan for f in g.get("files", [])):
        # an uploaded / renamed sheet ('A101.pdf', hashed copies) next to its model: stoa.kg finds sheets by the
        # model's name prefix, so it is not a plan node (Q 10:38: kg_qa fired 2/28 on hashed copies). Read its storey
        # with W1's plan_storey (sheet title, else GlobalId tags) and its cut-plane counts with W1's _cut_compare.
        try:
            import copy

            from stoa.kg.graph import _CHECK_KINDS, CUT_HEIGHT, _cut_compare, floor_offset
            from stoa.solvers.ifc.index import load_index
            from stoa.solvers.ifc.plan2d import plan_items
            from stoa.solvers.ifc.solver import plan_storey

            idx = load_index(g["model"])
            s, _why = plan_storey(this_plan, idx)
            if s is not None:
                g = copy.deepcopy(g)
                items = plan_items(this_plan)
                cut_z = (s.elevation or 0.0) + floor_offset(idx) + CUT_HEIGHT
                sname = {x.guid: x.name for x in idx.storeys}
                g.setdefault("files", []).append({"path": this_plan, "kind": "plan", "storey": s.guid})
                for st in g.get("storeys", []):
                    if st["guid"] == s.guid and not st.get("plan"):
                        st["plan"] = this_plan
                for r in g.get("rooms", []):
                    if r.get("storey") == s.guid and not r.get("plan"):
                        r["plan"] = this_plan
                        it = items.get(r.get("guid"))
                        if it is not None:
                            r["bbox_pt"] = [round(v, 2) for v in it.bbox]
                for label, classes in _CHECK_KINDS:
                    c = _cut_compare(idx, s.guid, items, classes, cut_z, sname)
                    if c["model"] or c["drawn_all"]:
                        g.setdefault("crosschecks", []).append({"storey": s.name, "what": label, "plan": this_plan, **c})
                this_extra = {"name": s.name, "guid": s.guid, "plan": this_plan, "why": _why}
        except Exception:  # noqa: BLE001  (never break the link route on an odd upload)
            this_extra = None
    rows: list[dict] = []

    def add(tag, text, **data):
        rows.append({"id": f"{tag}{sum(1 for r in rows if r['id'][0] == tag) + 1}", "text": text, **data})

    sto = {s["guid"]: s for s in g.get("storeys", [])}
    for f in g.get("files", []):
        k = f["kind"]
        st = sto.get(f.get("storey") or "", {}).get("name")
        txt = f"{KINDS.get(k, k)}: {Path(f['path']).name}" + (f" (storey '{st}')" if st else "")
        if f["path"] == this_plan:
            txt += " — THIS sheet (the one the question is asked on)"
        add("F", txt, kind=k, path=f["path"], storey=st)
    for p in g.get("same_building", []):
        add("F", f"same building in another dataset: {p}", kind="same-building", path=p, storey=None)
    for s in g.get("storeys", []):
        mc = s.get("model_counts", {})
        n_d = sum(v for k, v in mc.items() if k.startswith("IfcDoor"))
        n_w = sum(v for k, v in mc.items() if k.startswith("IfcWindow"))
        n_r = mc.get("IfcSpace", 0)
        add("S", f"storey '{s['name']}' elevation {s.get('elevation') or 0:.2f} m; plan sheet: "
                 f"{Path(s['plan']).name if s.get('plan') else 'NONE'}; in the IFC model: {n_d} doors, {n_w} windows, "
                 f"{n_r} rooms", storey=s["name"], plan=s.get("plan"), doors=n_d, windows=n_w, rooms=n_r)
    for c in g.get("crosschecks", []):
        if c["drawn_all"] == 0 and not c["model"]:
            continue
        tagged = c["drawn_all"] > 0
        txt = (f"{c['what']} on storey '{c['storey']}' (plan {Path(c['plan']).name}): IFC model {c['model']}; "
               f"{c['model_cut']} of them cut by the plan's section plane (floor +1.2 m), "
               f"{c['model'] - c['model_cut']} entirely above/below it; drawn on the plan: "
               + (f"{c['drawn']}" if tagged else "UNKNOWN (this sheet's vector data tags no " + c["what"] + ")"))
        if c.get("drawn_other"):
            txt += "; the plan also shows " + ", ".join(f"{n} {c['what']} of storey '{k}'"
                                                       for k, n in c["drawn_other"].items())
        add("C", txt, what=c["what"], storey=c["storey"], plan=c["plan"], model=c["model"], model_cut=c["model_cut"],
            drawn=c["drawn"] if tagged else None, drawn_other=sum((c.get("drawn_other") or {}).values()))
    for r in g.get("rooms", []):
        nm = " ".join(x for x in (r.get("long_name"), r.get("name")) if x)
        add("R", f"room '{nm}' on storey '{r['storey_name']}', {r.get('area_m2') or 0:g} m², plan sheet "
                 f"{Path(r['plan']).name if r.get('plan') else 'NONE'}", name=nm, storey=r["storey_name"],
            plan=r.get("plan"), bbox=r.get("bbox_pt"), guid=r.get("guid"), model=g.get("model"))
    return rows, {"model": g.get("model"),
                  "this": this_extra or (links(path).get("storey") if this_plan else None)}


def _retrieve(rows: list[dict], question: str, k: int = 12) -> list[dict]:
    """All F/S/C rows + the room rows whose name shares a token with the question (k at most)."""
    toks = {t for t in re.findall(r"[\w\-./]+", question.lower()) if len(t) >= 3}
    base = [r for r in rows if r["id"][0] != "R"]
    scored = []
    for r in rows:
        if r["id"][0] != "R":
            continue
        name = r["name"].lower()
        s = sum(1 for t in toks if t in name) + sum(2 for t in toks if t == name or f"'{t}'" in question.lower()
                                                    and t in name)
        ql = question.lower()
        s += sum(1 for nt in re.findall(r"[a-zäöüõåéèà]{4,}", name) if nt[:5] in ql)
        if s:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    rooms = [r for r in rows if r["id"][0] == "R"]
    if not scored and len(rooms) <= 80:
        return base + rooms  # no name overlap (e.g. 'Heizkesselraum' vs 'Boiler room'): let the model map it
    return base + [r for _, r in scored[:k]]


SCHEMA = {"type": "object", "properties": {
    "op": {"type": "string", "enum": ["count_rows", "lookup_storey", "lookup_sheet", "agree", "diff", "greater",
                                      "list_storeys", "exists", "none"]},
    "rows": {"type": "array", "items": {"type": "string"}},
    "a": {"type": "string", "enum": ["model", "model_cut", "drawn", "drawn_other", "none"]},
    "b": {"type": "string", "enum": ["model", "model_cut", "drawn", "drawn_other", "none"]},
    "why": {"type": "string"}}, "required": ["op", "rows", "a", "b"]}

PROMPT = """You answer questions about a building's DRAWING SET and IFC MODEL using only these fact rows.
F = files/sheets, S = storeys, C = model-vs-plan counts per storey, R = rooms.

{rows}

Question (any language): {q}

Return JSON {{"op", "rows", "a", "b", "why"}}. Pick ONE op and cite the row ids it needs; Python computes the answer:
- count_rows: how many sheets/storeys/rooms of some kind -> cite EVERY matching row (e.g. all floor plan sheet rows).
- lookup_storey / lookup_sheet: which storey / which sheet shows a room or storey -> cite the R (or S) row(s).
- agree: do the plan and the model agree on a count -> cite the one C row (Python compares model vs drawn).
- diff: a number like 'in the model but not drawn' -> cite the C row, a and b = the two quantities (a - b).
- greater: yes/no 'does A exceed B' -> cite the C row, a and b as above.
- list_storeys: name the storeys that satisfy a condition -> cite every matching S row.
- exists: yes/no 'is there a ...' -> cite the matching rows (none -> rows []).
- none: the rows cannot answer it.
Use a/b = "none" unless op is diff or greater."""


# --- v23 fixes (Q 09:45 + R1 probe_r1v5): comparatives, two-part questions, this sheet's storey, storey roles ---
# 'more/fewer ... than' in en/de/fi/fr/sv/it/nl/es/et: the yes/no is a comparison with a DIRECTION, never 'agree?'
_MORE = r"\b(more|mehr|enemmän|useampi\w*|plus|fler|più|meer|más|rohkem)\b"
_FEWER = r"\b(fewer|less|weniger|vähemmän|harvempi\w*|moins|färre|mindre|meno|minder|menos|vähem)\b"
_THAN = r"\b(than|als|kuin|que|qu'|än|di|che|dan|kui)\b"
_PLAN_SIDE = (r"\b(plan|floor ?plan|drawing|sheet|drawn|here|grundriss\w*|zeichnung\w*|gezeichnet|blatt|piirustu\w*|"
              r"pohja\w*|piirretty|dessin\w*|dessiné\w*|feuille|ritning\w*|ritad\w*|pianta|tavola|disegn\w*|tekening|"
              r"plattegrond|getekend|plano|dibujad\w*|joonis\w*)\b")
_MODEL_SIDE = r"\b(ifc|bim|model\w*|maquette|modell\w*|malli\w*|modèle|modello|modelo|mudel\w*)\b"
# 'this sheet / this plan / here': the storey of the sheet the question is asked on
_THIS = (r"\b(this|dieser|diesem|diesen|dieses|tämä\w*|tällä|tässä|ce|cette|denna|detta|den här|questa|questo|deze|"
         r"dit|este|esta|see|selle)\s+(plan\w*|floor ?plan|drawing|sheet|grundriss|zeichnung|blatt|piirustu\w*|"
         r"pohja\w*|feuille|dessin|ritning\w*|pianta|tavola|disegno|tekening|plattegrond|plano|dibujo|joonis\w*|"
         r"storey|floor|level|geschoss|kerros\w*|niveau|étage|våning|piano|verdieping|planta|korrus\w*)\b|\bhere\b")
# two questions in one ('Which storey does this sheet show, and does its door count match the model?')
_SPLIT = (r",?\s+(?:and|und|ja|et|och|e|en|y)\s+(?=(?:if so,?\s+|falls ja,?\s+|si oui,?\s+|om så,?\s+)?"
          r"(?:do|does|is|are|how|which|what|was|were|has|have|can|stimmt|stimmen|wie|welche\w*|ist|sind|hat|"
          r"onko|ovatko|täsmää\w*|kuinka|montako|est-ce|combien|quel\w*|stämmer|hur|vilke\w*|quant\w*|quale|"
          r"corrispond\w*|hoeveel|welke|klopt|kloppen|cuánt\w*|qué|cuál|coincid\w*|mitu|kas)\b)")
_BASEMENT_Q = (r"\b(basement|cellar|keller(geschoss)?|untergeschoss|kellari\w*|sous-sol|källar\w*|cantina|"
               r"seminterrato|kelder|sótano|kelder|kelder\w*|kelder)\b")
_BASEMENT_NAME = r"^\s*(kg|ug|u\d|b\d|-\d)(?![a-z0-9])|\b(keller|untergeschoss|basement|cellar|kellari|sous-sol|källare|kelder)\b"


_WHAT = {"doors": r"\b(doors?|türen?|ov(i|et|ia|ea)|portes?|dörr\w*|port[ae]|deur\w*|puertas?|uks\w*)\b",
         "windows": r"\b(windows?|fenster\w*|ikkun\w*|fenêtres?|fönster\w*|finestr\w*|ramen|raam|ventanas?|aken\w*)\b",
         "rooms": r"\b(rooms?|räume?n?|raum|huone\w*|pièces?|rum(men)?|stanz\w*|ruimtes?|habitaci\w*|ruum\w*|spaces?)\b",
         "walls": r"\b(walls?|wände|wand|seinä\w*|murs?|vägg\w*|mur[io]|muren|muur|paredes?|sein\w*)\b",
         "columns": r"\b(columns?|stützen?|säulen?|pilar\w*|poteaux?|pelare?|pilastr\w*|colonn\w*|kolom\w*|columnas?)\b"}


def _role_storey(question: str, rows: list[dict]) -> tuple[str | None, str]:
    """A storey ROLE word ('ground floor', 'Erdgeschoss', 'basement') -> the storey it names, with why. W1's rule
    (stoa.solvers.ifc.parse.storey_mention, KNOWLEDGE 09:36): a storey NAMED so (EG / GF / RDC / KG / UG / Keller),
    else the storey with rooms nearest elevation 0 (ground) / the lowest storey below 0 with rooms (basement)."""
    try:
        from stoa.solvers.ifc.parse import _GROUND_NAME, _GROUND_Q, fold, ground_reference
    except Exception:  # noqa: BLE001
        return None, ""
    t = " " + fold(question) + " "
    srows = [r for r in rows if r["id"][0] == "S"]
    if not srows:
        return None, ""
    elev = {}
    for r in srows:
        m = re.search(r"elevation (-?[\d.]+) m", r["text"])
        elev[r["storey"]] = float(m.group(1)) if m else 0.0
    m = _GROUND_Q.search(t)
    if m and not ground_reference(t, m.start()):
        named = [r["storey"] for r in srows if _GROUND_NAME.search(fold(r["storey"] or ""))]
        if len(named) == 1:
            return named[0], f"'{m.group(0).strip()}' = storey '{named[0]}' (named as the ground floor)"
        live = [r["storey"] for r in srows if r.get("rooms") or r.get("doors")] or [r["storey"] for r in srows]
        s = min(live, key=lambda n: abs(elev[n]))
        return s, f"'{m.group(0).strip()}' = storey '{s}' (the storey with rooms nearest elevation 0; assumed)"
    m = re.search(_BASEMENT_Q, t)
    if m:
        named = [r["storey"] for r in srows if re.search(_BASEMENT_NAME, fold(r["storey"] or ""))]
        if len(named) == 1:
            return named[0], f"'{m.group(0).strip()}' = storey '{named[0]}' (named as the basement)"
        below = [r["storey"] for r in srows if elev[r["storey"]] < -1.0 and (r.get("rooms") or r.get("doors"))]
        if below:
            s = max(below, key=lambda n: elev[n])  # the first storey below ground
            return s, f"'{m.group(0).strip()}' = storey '{s}' (the first storey below ground with rooms; assumed)"
    return None, ""


def _compare_sides(q: str) -> tuple[str, str, str] | None:
    """('drawn'|'model', '>'|'<', why) for 'does the plan show fewer X than the model' style questions."""
    mm, mf = re.search(_MORE, q), re.search(_FEWER, q)
    th = re.search(_THAN, q)
    if not (mm or mf) or not th:
        return None
    cmp_ = mm if (mm and (not mf or mm.start() < mf.start())) else mf
    if th.start() < cmp_.start():
        return None
    head = q[:th.start()]
    p, mo = re.search(_PLAN_SIDE, head), re.search(_MODEL_SIDE, head)
    if p and mo:
        subj = "drawn" if p.start() < mo.start() else "model"
    elif p or mo:
        subj = "drawn" if p else "model"
    else:
        tail = q[th.end():]
        p2, m2 = re.search(_PLAN_SIDE, tail), re.search(_MODEL_SIDE, tail)
        if bool(p2) == bool(m2):
            return None
        subj = "model" if p2 else "drawn"  # 'than the plan' -> the subject is the model's count
    op = ">" if cmp_ is mm else "<"
    return subj, op, f"'{cmp_.group(0)} … {th.group(0).strip()}': {subj} {op} {'model' if subj == 'drawn' else 'drawn'}"


def _first_sentence(s: str, n: int = 140) -> str:
    s = re.split(r"(?<=[.!?])\s+|\s+(?:But|However|Wait)\b", str(s).strip(), maxsplit=1)[0]
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


# 'Is there an IFC model / a DXF / a 3D model for this plan?' on a drawing with no project graph (Swiss Dwellings,
# CubiCasa, uploads): the answer is which files are linked to it (Q v23: right at 0.30-0.45 by luck, 0 evidence)
_EXISTS = (r"\b(is there|are there|does (it|this \w+) (have|come with)|do (we|you) have|exists?|is (an?|the) .{0,30} "
           r"available|gibt es|existiert|onko|löytyykö|y a-t-il|existe-t-il|finns det|c'è|esiste|is er|bestaat|hay|"
           r"existe|kas on)\b")
_FORMATS = (("IFC / 3D model", ".ifc", r"\b(ifc|bim|3d[- ]?(model\w*|file)|3-d model|building model|modell\w*|"
                                       r"model(e|o)?|maquette|malli\w*|mudel\w*)\b"),
            ("DXF / CAD drawing", ".dxf", r"\b(dxf|dwg|cad( file| drawing)?|vector (file|drawing))\b"),
            ("PDF sheet", ".pdf", r"\bpdf\b"),
            ("raster image", ".png", r"\b(png|jpe?g|raster image|bitmap)\b"))


def _file_exists_answer(path: str, question: str, t0: float) -> Answer | None:
    q = question.lower()
    if not re.search(_EXISTS, q):
        return None
    fmt = next(((name, ext) for name, ext, rx in _FORMATS if re.search(rx, q)), None)
    if fmt is None:
        return None
    try:
        from stoa.kg import links

        L = links(path) or {}
    except Exception:  # noqa: BLE001
        return None
    sib = dict(L.get("siblings") or {})
    if L.get("model"):
        sib.setdefault(".ifc", L["model"])
    have = sorted(Path(v).name for v in sib.values())
    yes = fmt[1] in sib
    src = L.get("source") or "unknown"
    known = src in ("swiss_dwellings", "cubicasa5k", "ifc_models", "ifc_bench")
    value = f"{'yes' if yes else 'no'} (files linked to this drawing: {', '.join(have) or 'none'})"
    return Answer(value=value, confidence=0.85 if known else 0.6, solver="kg_qa",
                  evidence=[Evidence(file=v, note=f"linked file ({k})") for k, v in sorted(sib.items())][:6],
                  trace=[f"kg_qa: does a {fmt[0]} exist for this drawing? linked files ({src}): {have} "
                         "(deterministic, no model call)"],
                  assumptions=[f"the drawing set = the files stored with this drawing ({src})"]
                  + ([] if known else ["only files next to this file were searched"]),
                  missing=([] if yes or known else [f"a {fmt[0]} stored elsewhere would not be found"]),
                  cost=Cost(wall_seconds=round(time.perf_counter() - t0, 3)))


def solve(path: str, question: str, backend: str = "local") -> Answer:
    """One link question; a two-part one ('Which storey …, and does …?') is answered part by part and joined."""
    parts = re.split(_SPLIT, question.strip(), maxsplit=1, flags=re.I)
    if len(parts) == 2 and len(parts[0].split()) >= 3 and len(parts[1].split()) >= 2:
        p1 = parts[0].rstrip(" ,;") + "?"
        p2 = re.sub(r"^(if so,?|falls ja,?|si oui,?|om så,?)\s+", "", parts[1].strip(), flags=re.I)
        a1 = _solve_one(path, p1, backend)
        a2 = _solve_one(path, p2, backend, llm_question=f"{question}\n(Answer ONLY its last part now: \"{p2}\")")
        if a1.value is None or a2.value is None:
            a = a1 if a2.value is None else a2
            a.confidence = min(a.confidence, 0.5)
            a.missing = [*a.missing, "two-part question: only one part could be answered from the linked facts"]
            a.trace = [f"kg_qa: two-part question -> '{p1}' | '{p2}'", *a.trace]
            return a
        a1.value = f"{a1.value}; {a2.value}"
        a1.unit = None
        a1.confidence = min(a1.confidence, a2.confidence)
        a1.evidence = (a1.evidence + [e for e in a2.evidence if e not in a1.evidence])[:12]
        a1.trace = [f"kg_qa: two-part question -> '{p1}' | '{p2}' (answered separately, joined)", *a1.trace,
                    *a2.trace]
        a1.missing = [*a1.missing, *a2.missing]
        c1, c2 = a1.cost, a2.cost
        a1.cost = Cost(llm_tokens_in=c1.llm_tokens_in + c2.llm_tokens_in, llm_tokens_out=c1.llm_tokens_out
                       + c2.llm_tokens_out, gpu_seconds=c1.gpu_seconds + c2.gpu_seconds,
                       api_calls=c1.api_calls + c2.api_calls, llm_calls=c1.llm_calls + c2.llm_calls,
                       wall_seconds=round(c1.wall_seconds + c2.wall_seconds, 3))
        return a1
    return _solve_one(path, question, backend)


def _solve_one(path: str, question: str, backend: str = "local", llm_question: str | None = None) -> Answer:
    t0 = time.perf_counter()
    from stoa.llm import chat, cost_meter, extract_json

    rows, ctx = facts(path)
    if not rows:
        fa = _file_exists_answer(path, question, t0)
        if fa is not None:
            return fa
        return Answer(value=None, confidence=0.0, solver="kg_qa", trace=["kg_qa: no project graph for this file"],
                      missing=["no linked model / sheet set for this drawing"])
    hit = is_link_question(question)
    want = _sheet_kinds(question)
    if want and ("count sheets" in hit["why"] or "sheet exists" in hit["why"]):
        # deterministic: no model call (sheet kinds come from the file names W1's graph already classified)
        got = [r for r in rows if r["id"][0] == "F" and r.get("kind") in want]
        if "count sheets" in hit["why"]:
            value, unit = len(got), "count"
        else:
            value, unit = ("yes" if got else "no"), None
        return Answer(value=value, unit=unit, confidence=0.85, solver="kg_qa",
                      evidence=[Evidence(file=r["path"], note=r["text"][:100]) for r in got][:12],
                      trace=[f"kg_qa: {hit['why']} -> files of kind {sorted(want)} in the project graph: "
                             f"{[Path(r['path']).name for r in got]} (deterministic, no model call)"],
                      assumptions=["the drawing set = every sheet rendered from this IFC model in the dataset"],
                      cost=Cost(wall_seconds=round(time.perf_counter() - t0, 3)))
    counting_q = bool(re.search(r"\b(how many|wie viele|kuinka monta|montako|combien|quant[ie]|hur många|hoeveel|mitu|"
                                r"kui palju|cuánt[oa]s)\b", question.lower()))
    if hit["why"] in ("storeys without rooms", "storeys without a plan") and not counting_q:
        key = "rooms" if hit["why"] == "storeys without rooms" else "plan"
        got = [r for r in rows if r["id"][0] == "S" and not r.get(key)]
        return Answer(value=", ".join(r["storey"] for r in got) if got else "none", confidence=0.8, solver="kg_qa",
                      evidence=[Evidence(file=ctx.get("model") or path, note=r["text"][:120]) for r in got][:12],
                      trace=[f"kg_qa: {hit['why']} -> storeys of the IFC model with no {key}: "
                             f"{[r['storey'] for r in got]} (deterministic, no model call)"],
                      cost=Cost(wall_seconds=round(time.perf_counter() - t0, 3)))
    lq = llm_question or question
    view = _retrieve(rows, lq)
    byid = {r["id"]: r for r in rows}
    role, role_why = _role_storey(question, rows)
    hint = []
    if role:
        # Q v23: 'Which sheet shows the ground floor?' on the 1.OG sheet -> the open sheet @0.85 (gold EG)
        srow = next(r for r in rows if r["id"][0] == "S" and r["storey"] == role)
        hint = [f"[H1] in this question {role_why}; its row is {srow['id']}"]
    with cost_meter() as m:
        res = chat(PROMPT.format(rows="\n".join([*(f"[{r['id']}] {r['text']}" for r in view), *hint]), q=lq),
                   backend=backend, max_tokens=400, temperature=0.0, json_schema=SCHEMA)
    js = extract_json(res.text) or {}
    if isinstance(js, list):
        js = next((x for x in js if isinstance(x, dict)), {})
    op = js.get("op", "none")
    ql = question.strip().lower()
    counting = bool(re.search(r"\b(how many|how much|count|number of|wie viele|anzahl|kuinka monta|montako|combien|"
                              r"nombre de|quant[ie]|numero di|hur många|antal|hoeveel|aantal|mitu|kui palju|cuánt[oa]s|"
                              r"número de)\b", ql))
    # 'Can you tell me how many …' is a count, not a yes/no (paraphrase: -> 'yes (model 20 vs drawn 10)' @0.8)
    ql_y = re.sub(r"^(can|could|would|will) you (please )?(tell me|say|count|give me|list|show me|find)\s+", "", ql)
    yesno = bool(re.match(_YESNO, ql_y)) or (not counting and op == "diff")
    trace_fix = None
    cmp_ = _compare_sides(ql) if (yesno and not counting) else None
    # 'the same storey / floor' names the storey, it is not 'agree' (Q v23: 'fewer windows than the IFC model has on
    # the same storey?' -> agree -> 'no (55 vs 52)')
    ql_agree = re.sub(r"\b(the )?(same|selben?|gleichen?|samma|même|stesso|zelfde|mismo|sama\w*)\s+"
                      r"(storey|story|floor|level|geschoss|stockwerk|etage|ebene|våning\w*|niveau|étage|piano|"
                      r"verdieping|planta|piso|kerros\w*|korrus\w*)\b", " ", ql)
    if cmp_ and op in ("agree", "diff", "greater"):
        op, trace_fix = "greater", f"comparative yes/no {cmp_[2]} (direction from the question, not the model)"
    elif yesno and op in ("diff", "greater") and re.search(_AGREE_ONLY, ql_agree):
        op, trace_fix = "agree", f"yes/no 'all/every/agree' question: {op} -> agree"
    elif yesno and op == "diff":
        op, trace_fix = "greater", "yes/no question: diff -> greater"
    cited = [byid[i.strip("[] ")] for i in js.get("rows", []) if i.strip("[] ") in byid]
    trace = [f"kg_qa: {len(rows)} fact rows ({len(view)} shown); op {op} on {[r['id'] for r in cited]}"]
    if trace_fix:
        trace.append("kg_qa: " + trace_fix)
    this = (ctx.get("this") or {}).get("name")
    try:
        from stoa.solvers.ifc.parse import quoted_names
        named = quoted_names(question)
    except Exception:  # noqa: BLE001
        named = []
    st_names = [r["storey"] for r in rows if r["id"][0] == "S"]
    names_other = [n for n in st_names if n and n != this and re.search(
        r"(?<![\w.])" + re.escape(n.lower()) + r"(?![\w])", ql)]
    if (op in ("agree", "diff", "greater") and this and re.search(_THIS, ql) and not names_other
            and not (role and role != this) and not [n for n in named if n != this]):
        # Q v23 'Are there windows in the 3D model that this sheet does not draw?' cited 2.korrus's row (60 vs 53)
        cs = [r for r in cited if r["id"][0] == "C"]
        if cs and cs[0]["storey"] != this:
            own = next((r for r in rows if r["id"][0] == "C" and r["storey"] == this and r["what"] == cs[0]["what"]),
                       None)
            if own:
                cited = [own, *[r for r in cited if r is not cs[0]]]
                trace.append(f"kg_qa: 'this sheet' = storey '{this}': {cs[0]['id']} ('{cs[0]['storey']}') -> {own['id']}")
    q_st = [n for n in named if n in st_names]
    target = q_st[0] if len(set(q_st)) == 1 else (role or (this if not names_other and not q_st else None))
    assign_q = re.search(r"(not|n't|nicht|ei|pas|non|inte|niet|no)\b.{0,40}(assign|belong|zugeordnet|kuulu|attribu|"
                         r"assegn|tilldela|toegewezen|asign|recogni|määrat)", ql)
    if (op == "none" or not [r for r in cited if r["id"][0] == "C"]) and yesno and target and \
            re.search(_MODEL2, ql) and (cmp_ or assign_q or re.search(_AGREE_ONLY, ql_agree) or re.search(_AGREE, ql)):
        # the model cited no C row (r1v5 'Does this plan show more doors than the IFC model has on the same floor?',
        # Swedish 'Stämmer antalet fönster på ritningen med IFC-modellen för våningen …?' -> op none under load):
        # the storey (quoted / role / this sheet's) + the element word in the question pick the row deterministically
        what = next((w for w, rx in _WHAT.items() if re.search(rx, ql)), None)
        own = next((r for r in rows if r["id"][0] == "C" and r["storey"] == target and r["what"] == what), None)
        if own:
            op, cited = ("greater" if (cmp_ or assign_q) else "agree"), [own]
            trace.append(f"kg_qa: no C row cited -> {own['id']} ({what} on storey '{own['storey']}', deterministic)")
    if role and op in ("agree", "diff", "greater") and not named and not names_other:
        cs = [r for r in cited if r["id"][0] == "C"]
        if cs and cs[0]["storey"] != role:
            own = next((r for r in rows if r["id"][0] == "C" and r["storey"] == role and r["what"] == cs[0]["what"]),
                       None)
            if own:
                cited = [own, *[r for r in cited if r is not cs[0]]]
                trace.append(f"kg_qa: storey role {role_why}: {cs[0]['id']} -> {own['id']}")
    if role and not counting and not re.search(_ROOMW, ql) and not named and (
            op in ("lookup_sheet", "lookup_storey") or (op == "none" and (re.search(_WHICH_SHEET, ql) or re.search(
                _SHEET3, ql)))):  # W1 c8: 'How many walls on the ground floor?' must not become a sheet lookup
        srow = next(r for r in rows if r["id"][0] == "S" and r["storey"] == role)
        if {r.get("storey") for r in cited} != {role}:
            trace.append(f"kg_qa: storey role {role_why}: {[r['id'] for r in cited]} -> {srow['id']}")
            cited, op = [srow], ("lookup_sheet" if op == "none" else op)
    value, unit, conf, ev, missing = None, None, 0.0, [], []

    def evid(r, note):
        if r["id"][0] == "R" and r.get("plan") and r.get("bbox"):
            return Evidence(file=r["plan"], page=0, bbox=r["bbox"], bbox_space="pdf_pt", note=note)
        if r["id"][0] == "R" and r.get("guid") and r.get("model"):
            return Evidence(file=r["model"], ifc_guid=r["guid"], note=note)
        f = r.get("path") or r.get("plan")
        return Evidence(file=f, note=note) if f else None

    if op == "count_rows" and cited and all(r["id"][0] == "F" for r in cited):
        # sheets: Python decides which file kinds the question counts; the LLM only said 'count sheets'
        want = _sheet_kinds(question)
        if want:
            cited = [r for r in rows if r["id"][0] == "F" and r.get("kind") in want]
            trace.append(f"kg_qa: counting every file of kind {sorted(want)}")
        else:
            cited = [r for r in cited if r.get("kind") not in ("model", "same-building", "discipline-model")]
    if op == "count_rows" and cited:
        kinds = {r["id"][0] for r in cited}
        if len(kinds) == 1:
            value, unit, conf = len({r["id"] for r in cited}), "count", 0.8
            ev = [e for r in cited if (e := evid(r, r["text"][:80]))]
    elif op in ("lookup_storey", "lookup_sheet") and cited:
        # the sheet of a cited row: R/S rows carry 'plan'; F rows ARE the sheet ('path', kind plan/section/elevation)
        def sheet_of(r):
            if r["id"][0] == "F":
                return r.get("path") if r.get("kind") in ("plan", "section", "elevation", "raster-plan") else None
            if r.get("plan"):
                return r["plan"]
            # a room/storey row without a plan: the storey's own plan sheet, if any (S row of the same storey)
            srow = next((x for x in rows if x["id"][0] == "S" and x.get("storey") == r.get("storey")), None)
            return srow.get("plan") if srow else None

        asks_sheet = op == "lookup_sheet" or bool(re.search(_WHICH_SHEET, ql) or re.search(_SHEET3, ql))
        st = sorted({r.get("storey") for r in cited if r.get("storey")})
        sheets = sorted({(_short(x) if "_plan-" in Path(x).stem or "_section-" in Path(x).stem or "_elevation-" in
                          Path(x).stem else Path(x).name) for r in cited if (x := sheet_of(r))})
        if asks_sheet and sheets:
            # dataset sheets are '<model>_plan-NN-<storey>'; an upload keeps its own name ('A101', a hash)
            value = ", ".join(x for x in sheets)
            if st:
                value += " (storey " + ", ".join(f"'{s}'" for s in st) + ")"
            conf = 0.85 if len(sheets) == 1 else 0.5
        elif asks_sheet and st:
            value = "; ".join(f"storey '{s}'" for s in st) + " (no plan sheet for it in this set)"
            conf = 0.6
        elif st:
            value = ", ".join(st)
            conf = 0.85 if len(st) == 1 else 0.5
        if value is not None:
            ev = [e for r in cited if (e := evid(r, r["text"][:80]))]
            if op == "lookup_storey" and asks_sheet:
                trace.append("kg_qa: question asks for a sheet -> sheet formatting")
    elif (op in ("diff", "greater") and len({r["storey"] for r in cited if r["id"][0] == "C"}) >= 2
          and len({r["what"] for r in cited if r["id"][0] == "C"}) == 1):
        # two storeys compared ('How many more doors are on '1.korrus' than on '5.korrus'?'): model counts, in the
        # order the question names the storeys (was C1 model - C1 drawn = 0 @0.8, v17)
        cs = {r["storey"]: r for r in cited if r["id"][0] == "C"}
        order = sorted(cs, key=lambda s: (ql.find(s.lower()) if s.lower() in ql else 10 ** 6))
        c1, c2 = cs[order[0]], cs[order[1]]
        d = c1["model"] - c2["model"]
        if op == "diff":
            value, unit, conf = d, "count", 0.8
        else:
            mm_, mf_ = re.search(_MORE, ql), re.search(_FEWER, ql)
            fewer = bool(mf_) and not (mm_ and mm_.start() < mf_.start())
            value, conf = ("yes" if (d < 0 if fewer else d > 0) else "no") + f" ('{c1['storey']}' {c1['model']} vs " \
                f"'{c2['storey']}' {c2['model']} {c1['what']} in the IFC model)", 0.75
        ev = [Evidence(file=c1["plan"], note=c1["text"][:160]), Evidence(file=c2["plan"], note=c2["text"][:160])]
        trace.append(f"kg_qa: two storeys compared: '{c1['storey']}' {c1['model']} - '{c2['storey']}' {c2['model']}")
    elif op in ("agree", "diff", "greater") and len([r for r in cited if r["id"][0] == "C"]) >= 1:
        c = next(r for r in cited if r["id"][0] == "C")
        if c.get("drawn") is None:
            missing.append(f"this sheet's vector data does not tag {c['what']}: the drawn count cannot be compared")
            conf = 0.2
            trace.append("kg_qa: drawn count unknown")
        elif op == "agree":
            same = c["model"] == c["drawn"]
            value = "yes" if same else "no"
            why = (f"IFC model {c['model']} {c['what']} on '{c['storey']}', plan draws {c['drawn']}")
            if not same and c["model_cut"] == c["drawn"]:
                why += (f"; the other {c['model'] - c['model_cut']} lie entirely above/below the plan's 1.2 m section "
                        "plane, so the drawing is consistent with the model")
            value = f"{value} ({why})"
            conf = 0.85
        else:
            a, b = js.get("a", "model"), js.get("b", "drawn")
            if a == "none" or b == "none" or a == b:
                a, b = "model", "drawn"
            va, vb = c.get(a), c.get(b)
            if re.search(r"(not|n't|nicht|ei|pas|non|inte|niet|no)\b.{0,40}(assign|belong|zugeordnet|kuulu|attribu|"
                         r"assegn|tilldela|toegewezen|asign|recogni|määrat)", question.lower()):
                # elements DRAWN on this plan that the model puts on another storey (crossing the cut plane)
                a, va, b, vb = "drawn from other storeys", c.get("drawn_other", 0), "zero", 0
                trace.append("kg_qa: question asks about drawn elements of other storeys -> drawn_other")
            if cmp_ and op == "greater" and a != "drawn from other storeys":
                subj, rel = cmp_[0], cmp_[1]
                a, b = subj, ("model" if subj == "drawn" else "drawn")
                va, vb = c.get(a), c.get(b)
                if va is not None and vb is not None:
                    yes = va > vb if rel == ">" else va < vb
                    word = "more" if rel == ">" else "fewer"
                    side = {"drawn": "the plan draws", "model": "the IFC model has"}
                    rel_txt = ("the same number" if va == vb else ("more" if va > vb else "fewer"))
                    value = (f"{'yes' if yes else 'no'} ({side[a]} {va} {c['what']} on '{c['storey']}', "
                             f"{side[b]} {vb}: {rel_txt}" + (f", not {word})" if not yes else ")"))
                    conf = 0.85
                    va = vb = None  # done
            if va is not None and vb is not None:
                if op == "diff":
                    value, unit, conf = va - vb, "count", 0.8
                else:
                    value, conf = ("yes" if va > vb else "no") + f" ({a} {va} vs {b} {vb})", 0.8
        if value is not None:
            ev = [Evidence(file=c["plan"], note=c["text"][:160])]
    elif op == "list_storeys" and cited:
        st = [r["storey"] for r in cited if r["id"][0] == "S"]
        if st:
            value, conf = ", ".join(st), 0.75
    elif op == "exists":
        value, conf = ("yes" if cited else "no"), 0.7
        ev = [e for r in cited if (e := evid(r, r["text"][:80]))]
    if value is not None and not yesno and re.match(r"(yes|no)\b", str(value)) and re.match(
            r"(which|what|where|on which|in which|welche\w*|auf welche\w*|in welche\w*|mikä|missä|mill\w*|quel\w*|"
            r"sur quel\w*|vilke\w*|på vilke\w*|qual\w*|su qual\w*|welk\w*|op welk\w*|qué|cuál\w*|en qué|mis|"
            r"millis\w*)\b", ql):
        # Q 10:40 'Which floor has the biggest room?' -> 'yes (model 55 vs drawn 52)' @0.80: a which-question has no yes
        trace.append(f"kg_qa: which-question answered '{str(value)[:30]}' (op {op}) -> no answer")
        value, conf = None, 0.0
    if counting_q and value is not None and op in ("lookup_storey", "lookup_sheet", "list_storeys"):
        # W1 c8 'How many walls are there on the ground floor?' -> 'EG' @0.85 (a storey lookup): a count needs a number
        trace.append(f"kg_qa: count question answered with '{value}' (op {op}) -> no answer")
        value, conf = None, 0.0
    if value is None and not missing:
        missing.append("the linked sheet set / model facts do not answer this question")
    cost = Cost(llm_tokens_in=m.llm_tokens_in, llm_tokens_out=m.llm_tokens_out, gpu_seconds=m.gpu_seconds,
                api_calls=m.api_calls, llm_calls=m.calls, wall_seconds=round(time.perf_counter() - t0, 3))
    trace.append(f"kg_qa: why: {_first_sentence(js.get('why', ''))}")  # W5 09:33: one sentence on the card
    return Answer(value=value, unit=unit, confidence=conf if value is not None else min(conf, 0.2),
                  evidence=ev[:12], trace=trace, solver="kg_qa", missing=missing, cost=cost,
                  assumptions=["counts of 'drawn' elements come from the sheet's vector twin (IFC GUID per element)"])


if __name__ == "__main__":
    a = solve(sys.argv[1], sys.argv[2])
    print(is_link_question(sys.argv[2]))
    print(a.model_dump_json(indent=1)[:2500])
