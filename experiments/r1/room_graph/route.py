"""When should the pipeline hand a raster question to room_graph.solve()?  A text-only trigger + a file gate.

    from experiments.r1.room_graph.route import per_room
    hit = per_room(question, path)   # -> {"fire": bool, "kind": str, "room": str, "why": str}
    if hit["fire"]:
        ans = experiments.r1.room_graph.answer.solve(path, question)

It fires when a question is SCOPED to one room (or compares rooms), which drawing-level keys cannot answer:
  owner     "How many windows does the kitchen have?", "doors of the bathroom (KPH)", "windows in the bedrooms"
  relation  "Which room is the sauna entered from?", "rooms that open onto the hall", "next to the kitchen"
  locate    "In which room is the bathtub?", "How many rooms contain a toilet seat?"
  superlative "Which is the largest room?", "the biggest bedroom"
  room_area "What is the area of the kitchen?", "combined area of the living room and the kitchen"
It does NOT fire on whole-plan wordings ("How many bedrooms are on this floor plan?", "windows in the apartment",
"sinks (kitchen and bathroom combined)"); measured false-fire rate on every dataset/dev/hard split is in
research/methods.md 8j.  English is the main path (the pipeline translates other languages first); a few fi/de/
fr/sv/it forms are covered because those languages are not translated.

File gate: raster images only (.png/.jpg/.jpeg/.webp).  The room graph runs a CubiCasa5K segmentation (D8: cc5k=1
path only); on non-cubicasa rasters it still runs but is unmeasured, so `in_domain` tells the caller.
"""

from __future__ import annotations

import re
from pathlib import Path

# room nouns that can OWN things (container / scope).  Not: plan, drawing, apartment, flat, unit, floor, building.
_ROOM_EN = (r"(?:master\s+)?bed\s?rooms?|living\s?rooms?|lounge|sitting\s+rooms?|family\s+rooms?|kitchens?|kitchenette|"
            r"bath\s?rooms?|wash\s?rooms?|shower\s+rooms?|saunas?|steam\s+rooms?|toilet\s+rooms?|wc\s+rooms?|"
            r"wc(?!\s*(?:-\s*)?(?:seats?|bowls?|pans?|istuin))|lavatory|restroom|"
            r"(?:entrance|entry)\s+(?:hall(?:way)?|area|lobby)|hall(?:way)?s?|entry|entrance|corridors?|foyer|lobby|"
            r"vestibule|walk-?in(?:\s+(?:closet|wardrobe))?|closets?|wardrobes?|dressing\s+rooms?|"
            r"storage(?:\s+rooms?)?|store\s?rooms?|utility\s+rooms?|laundry(?:\s+rooms?)?|dining\s+(?:rooms?|area)|"
            r"study|office|studio\s+room|balcon(?:y|ies)|terraces?|porch(?:es)?|patio|veranda|loggia|garage|"
            r"rooms?\s+(?:labell?ed|marked|called|named)\s+\S+|rooms?\s*['\"“‘«][^'\"”’»]{1,30}['\"”’»]|"
            r"rooms?\s+[A-Z]{1,4}\d*\b")
_DET = r"(?:the|this|that|these|those|each|every|both|all(?:\s+the)?|its|their|your|a|an|one|any)"
_NUMW = r"(?:two|three|four|five|2|3|4|5)"
_ROOM = rf"(?:{_DET}\s+)?(?:{_NUMW}\s+)?(?:(?:small|smaller|large|larger|big|bigger|main|second|other|first|upper|lower|front|back|north|south|east|west)\w*\s+)?(?:{_ROOM_EN})"

_OWNER = [
    # "does the kitchen have", "do the two bedrooms have", "has the bathroom got"
    rf"\b(?:does|do|did|has|have)\s+{_ROOM}\s*(?:\([^)]{{1,30}}\)\s*)?(?:have|has|got|contain|include|feature)\b",
    # "windows in the kitchen", "doors of the bathroom", "the door into the sauna"
    rf"\b(?:in|inside|within|of|into|for|belonging\s+to|serving|on)\s+{_ROOM}\b",
    # "the kitchen's windows"
    rf"\b(?:{_ROOM_EN})['’]s?\s+(?:windows?|doors?|area|size|floor\s+area|toilets?|sinks?|fixtures?)\b",
]
_RELATION = [
    r"\b(?:entered|accessed|reached|reachable|accessible|approached|connected|entered)\s+(?:from|through|via|by|off)\b",
    r"\b(?:enter|reach|access|get\s+(?:in)?to|go\s+(?:in)?to|walk\s+(?:in)?to|step\s+(?:out\s+)?(?:on|in)?to)\b[^?]{0,40}\b(?:from|through|via)\b",
    r"\b(?:through|from|via|off|to)\s+which\s+(?:room|space|area)s?\b",
    r"\bwhich\s+(?:room|space|area)s?\b[^?]{0,60}\b(?:next\s+to|adjacent|beside|neighbou?r|border|connect|open|lead|"
    r"enter|access|reach|adjoin|between|share|lead)",
    r"\b(?:next\s+to|adjacent\s+to|beside|adjoining|bordering|neighbou?ring|connected\s+to|opens?\s+(?:directly\s+)?"
    r"(?:on)?(?:to|into)|leads?\s+(?:in)?to|between)\s+{room}".format(room=_ROOM),
    r"\bstep\s+out\s+(?:on)?to\b",
    # added after route_probe2 (untouched recall 19/24 before these): reachable without, share a wall, "A and B adjacent"
    r"\b(?:reachable|accessible)\s+(?:only\s+)?(?:from|through|via|without|by)\b",
    r"\bshares?\s+(?:a\s+|any\s+)?walls?\b",
    rf"\b(?:are|is)\s+{_ROOM}\s+and\s+{_ROOM}\s+(?:directly\s+)?(?:adjacent|connected|next\s+to\s+each\s+other|neighbou?rs?)\b",
    r"\b(?:rooms?|spaces?|doors?)\s+(?:open|lead|connect)s?\s+(?:directly\s+)?(?:on)?(?:to|into|off|from)\b",
    r"\b(?:rooms?|spaces?)\s+(?:off|around|along)\s+(?:the\s+)?(?:hall|corridor|entrance|lobby|foyer)",
]
_LOCATE = [
    r"\b(?:in|inside)\s+which\s+(?:room|space)s?\b",
    r"\bwhich\s+(?:room|space)s?\s+(?:is|are|contains?|has|have|holds?|houses?)\b",
    r"\b(?:how\s+many|which|what)\s+(?:rooms?|spaces?)\s+(?:in\s+[^?]{0,30}\s+)?(?:contain|have|has|hold|with|include)\b",
    # "How many bedrooms have a window?" (not "how many bedrooms are there / does the flat have")
    rf"\bhow\s+many\s+(?:of\s+the\s+)?(?:{_ROOM_EN})\s+(?:have|has|contain|include|are\s+(?:next|adjacent|connected|"
    r"reachable|accessible|entered|accessed))\b",
    r"\bwhere(?:\s+(?:is|are)|['’]s)\s+(?:the\s+)?(?:bath\s?tub|shower|toilet|wc|sink|stove|oven|sauna|fridge|washing\s+machine|kitchen|bedroom|bathroom)",
]
_SUPER = [
    rf"\b(?:largest|biggest|smallest|widest|narrowest|longest|brightest)\s+(?:{_ROOM_EN}|room|space)\b",
    r"\bwhich\s+(?:\w+\s+){0,2}(?:room|bedroom|space)s?\b[^?]{0,40}\b(?:largest|biggest|smallest|most|fewest|least)\b",
    r"\b(?:room|bedroom)s?\s+(?:with|has|have)\s+the\s+(?:most|fewest|largest|biggest|smallest)\b",
]
_AREA = [
    rf"\b(?:area|size|floor\s+area|surface|square\s+(?:metres|meters|feet|footage)|m2|m²|dimensions?|width|length)"
    rf"\s+(?:of|for)\s+{_ROOM}\b",
    rf"\bhow\s+(?:big|large|wide|long)\s+(?:is|are)\s+{_ROOM}\b",
]

# a few non-English forms (fi/de/fr/sv/it are NOT translated by the pipeline's front end)
_ROOM_FI = (r"(?:keittiö|makuuhuonee|olohuonee|kylpyhuonee|pesuhuonee|saunaa?|eteise|eteisaula|parvekkee|"
            r"wc:|vaatehuonee|kodinhoitohuonee|työhuonee|ruokailutila|halli)")
_OTHER = [
    # Finnish locative cases on a room noun: keittiössä / makuuhuoneessa / saunasta / eteiseen / parvekkeelle
    rf"\b{_ROOM_FI}(?:ssa|ssä|sta|stä|seen|hen|lla|llä|lle|lta|ltä|n\s+kautta)\b",
    r"\b(?:mistä|minkä|mihin|missä)\s+(?:huoneesta|huoneen|huoneeseen|huoneessa|tilasta|tilan)\b",
    r"\b(?:suurin|pienin|isoin)\s+(?:huone|makuuhuone|tila)\b",
    # German
    r"\b(?:in|im|in\s+der|in\s+dem|aus\s+der|aus\s+dem|vom|von\s+der|zum|zur|des|der)\s+"
    r"(?:küche|schlafzimmer[ns]?|wohnzimmer[ns]?|bad(?:ezimmer[ns]?)?|sauna|flur[es]?|diele|balkon[es]?|"
    r"abstellraum[es]?|ankleide|gäste-?wc|wc-raum)\b",
    r"\b(?:welche[mnrs]?|von\s+welchem|durch\s+welchen|in\s+welchem)\s+(?:raum|zimmer)\b",
    r"\b(?:größte[nrs]?|kleinste[nrs]?)\s+(?:raum|zimmer|schlafzimmer)\b",
    r"\bwie\s+(?:groß|gross|breit|lang)\s+(?:ist|sind)\s+(?:die|das|der)\s+(?:küche|schlafzimmer|wohnzimmer|bad|"
    r"badezimmer|sauna|flur|diele|balkon|abstellraum|ankleide|wc)\b",
    # French
    r"\b(?:dans|de|depuis|par)\s+(?:la|le|l['’])\s*(?:cuisine|chambre|salon|séjour|salle\s+de\s+bains?|salle\s+d['’]eau|"
    r"sauna|entrée|couloir|balcon|buanderie|dressing)\b",
    r"\bquelle\s+pièce\b|\bplus\s+grande\s+pièce\b",
    # Swedish
    r"\b(?:i|från|till|genom)\s+(?:köket|sovrummet|sovrummen|vardagsrummet|badrummet|bastun|hallen|balkongen|"
    r"tvättstugan|klädkammaren)\b",
    r"\bvilket\s+rum\b|\bstörsta\s+rummet\b",
    # Italian
    r"\b(?:nella|nel|nello|della|del|dallo|dalla|dal)\s+(?:cucina|camera(?:\s+da\s+letto)?|soggiorno|bagno|sauna|"
    r"ingresso|corridoio|balcone|ripostiglio|lavanderia)\b",
    r"\b(?:quale|in\s+quale|da\s+quale)\s+(?:stanza|locale|ambiente)\b|\b(?:stanza|locale)\s+più\s+grande\b",
]

# whole-plan wordings that must win even if a pattern above matches (e.g. 'kitchen and bathroom combined')
_WHOLE = [
    r"\((?:[^)]*\b(?:kitchen\s+and\s+bathroom|keittiö\s+ja\s+kylpy)[^)]*)\)",
]

_KINDS = [("relation", _RELATION), ("locate", _LOCATE), ("superlative", _SUPER), ("room_area", _AREA),
          ("owner", _OWNER), ("other_lang", _OTHER)]
_COMPILED = [(k, [re.compile(p, re.I) for p in ps]) for k, ps in _KINDS]
_WHOLE_RE = [re.compile(p, re.I) for p in _WHOLE]
_COUNT_OF = re.compile(r"\b(?:number|count|total|amount|quantity|sum|tally|list)\s*$", re.I)
_RASTER = {".png", ".jpg", ".jpeg", ".webp"}


def text_trigger(question: str) -> dict:
    """Text only: {"fire", "kind", "match"}.  Parenthesised whole-plan clauses are removed first."""
    q = question
    for w in _WHOLE_RE:
        q = w.sub(" ", q)
    for kind, pats in _COMPILED:
        for p in pats:
            for m in p.finditer(q):
                # "the number of balconies in this drawing" is a whole-plan count, not "the doors of the balcony"
                if kind == "owner" and m.group(0).lower().startswith("of") and _COUNT_OF.search(q[:m.start()]):
                    continue
                return {"fire": True, "kind": kind, "match": m.group(0)}
    return {"fire": False, "kind": "", "match": ""}


def per_room(question: str, path: str | Path | None = None) -> dict:
    """Route test: fire only on raster images.  in_domain = CubiCasa-style plan (the room graph was measured there)."""
    t = text_trigger(question)
    p = str(path or "")
    raster = Path(p).suffix.lower() in _RASTER if p else True
    in_domain = "cubicasa" in p.lower() or not p
    fire = bool(t["fire"] and raster)
    why = (f"question scoped to a room ({t['kind']}: '{t['match']}')" if t["fire"] else "no room scope")
    if t["fire"] and not raster:
        why += "; not a raster image (use the vector/IFC solvers)"
    return {"fire": fire, "kind": t["kind"], "match": t["match"], "in_domain": in_domain, "why": why}


if __name__ == "__main__":
    import sys
    print(per_room(" ".join(sys.argv[2:]), sys.argv[1]))
