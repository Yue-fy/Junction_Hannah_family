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
                 r"plattegrond\w*|plan d'étage|plans d'étage)\b", q):
        want.add("plan")
    if re.search(r"\b(sections?|sectional|schnitt\w*|leikkau\w*|coupes?|sektion\w*|snitt\w*|sezion\w*|doorsnede\w*|"
                 r"lõike\w*|secci\w*|corte\w*)\b", q):
        want.add("section")
    if re.search(r"\b(elevations?|ansicht\w*|julkisivu\w*|façades?|facades?|fasad\w*|prospett\w*|gevel\w*)\b", q):
        want.add("elevation")
    if re.search(r"\b(in total|all|altogether|insgesamt|alle|yhteensä|kaikki|au total|tous|totalt|alla|in totale|"
                 r"tutti|totaal|kokku)\b", q) and re.search(r"\b(sheets?|drawings?|blätter|piirustu\w*|feuilles?)\b", q):
        want |= {"plan", "section", "elevation"}
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
                                                     r"mehr|weniger|meisten|enemmän|vähemmän|eniten|plus de|moins de|"
                                                     r"flest|fler|più|meno|meer|minder|rohkem)\b", q) and (re.search(r"['\"‘’“”]", q) or re.search(
            r"(\broom|raum\b|huone|\bpièce|\bsalle|\blocal|rum(met)?\b|\bstanza|ruimte\b|ruum\b)", q)):
        why.append("room -> storey/sheet")
    if not why and re.search(_MODEL2, q) and re.search(_PLAN2, q):
        why.append("plan and model named")
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
    return rows, {"model": g.get("model"), "this": links(path).get("storey") if this_plan else None}


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


def solve(path: str, question: str, backend: str = "local") -> Answer:
    t0 = time.perf_counter()
    from stoa.llm import chat, cost_meter, extract_json

    rows, ctx = facts(path)
    if not rows:
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
    view = _retrieve(rows, question)
    byid = {r["id"]: r for r in rows}
    with cost_meter() as m:
        res = chat(PROMPT.format(rows="\n".join(f"[{r['id']}] {r['text']}" for r in view), q=question),
                   backend=backend, max_tokens=400, temperature=0.0, json_schema=SCHEMA)
    js = extract_json(res.text) or {}
    if isinstance(js, list):
        js = next((x for x in js if isinstance(x, dict)), {})
    op = js.get("op", "none")
    ql = question.strip().lower()
    counting = bool(re.search(r"\b(how many|how much|count|number of|wie viele|anzahl|kuinka monta|montako|combien|"
                              r"nombre de|quant[ie]|numero di|hur många|antal|hoeveel|aantal|mitu|kui palju|cuánt[oa]s|"
                              r"número de)\b", ql))
    yesno = bool(re.match(_YESNO, ql)) or (not counting and op == "diff")
    trace_fix = None
    if yesno and op in ("diff", "greater") and re.search(_AGREE_ONLY, ql):
        op, trace_fix = "agree", f"yes/no 'all/every/agree' question: {op} -> agree"
    elif yesno and op == "diff":
        op, trace_fix = "greater", "yes/no question: diff -> greater"
    cited = [byid[i.strip("[] ")] for i in js.get("rows", []) if i.strip("[] ") in byid]
    trace = [f"kg_qa: {len(rows)} fact rows ({len(view)} shown); op {op} on {[r['id'] for r in cited]}"]
    if trace_fix:
        trace.append("kg_qa: " + trace_fix)
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
        sheets = sorted({_short(x) for r in cited if (x := sheet_of(r))})
        if asks_sheet and sheets:
            value = ", ".join(f"plan-{x}" if not x.startswith(("plan", "section", "elevation")) else x for x in sheets)
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
    if value is None and not missing:
        missing.append("the linked sheet set / model facts do not answer this question")
    cost = Cost(llm_tokens_in=m.llm_tokens_in, llm_tokens_out=m.llm_tokens_out, gpu_seconds=m.gpu_seconds,
                api_calls=m.api_calls, llm_calls=m.calls, wall_seconds=round(time.perf_counter() - t0, 3))
    trace.append(f"kg_qa: why: {str(js.get('why', ''))[:160]}")
    return Answer(value=value, unit=unit, confidence=conf if value is not None else min(conf, 0.2),
                  evidence=ev[:12], trace=trace, solver="kg_qa", missing=missing, cost=cost,
                  assumptions=["counts of 'drawn' elements come from the sheet's vector twin (IFC GUID per element)"])


if __name__ == "__main__":
    a = solve(sys.argv[1], sys.argv[2])
    print(is_link_question(sys.argv[2]))
    print(a.model_dump_json(indent=1)[:2500])
