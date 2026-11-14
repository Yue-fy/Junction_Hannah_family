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
from stoa.solvers.raster import textlayer as T

PROMPT = """You answer a question about a scanned technical drawing (architecture / engineering).
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
[] if it comes only from the image>], "assumptions": "<what you assumed, or empty>"}}"""

SCHEMA = {"type": "object", "properties": {
    "answer": {"type": "string", "maxLength": 200},
    "unit": {"type": "string", "maxLength": 12},
    "lines": {"type": "array", "items": {"type": "integer"}, "maxItems": 8},
    "assumptions": {"type": "string", "maxLength": 300}},
    "required": ["answer", "unit", "lines", "assumptions"]}

_NUM = re.compile(r"^\s*-?\d+(?:[.,]\d+)?\s*$")


def facts(tl: T.TextLayer) -> str:
    out = []
    sc = T.scales(tl)
    if sc:
        out.append("Scale notes found: " + "; ".join(f"'{s['line'][:50]}' = 1:{s['ratio']:g}" for s in sc[:3]) + ".")
    else:
        out.append("No scale note was found in the texts.")
    ar = T.areas(tl)
    if ar:
        out.append(f"Printed areas: {len(ar)} (e.g. " + ", ".join(a["line"][:30] for a in ar[:4]) + ").")
    return "\n".join(out)


def answer(path: str, question: str, image_path: str | None = None, backend: str = "local",
           max_texts: int = 160, solver: str = "raster") -> Answer:
    tl = T.text_layer(image_path or path)
    W, H = tl.size
    items = tl.items[:max_texts]
    texts = "\n".join(f"[{k}] ({100 * i.cx / W:.0f}%, {100 * i.cy / H:.0f}%) {i.text[:100]}" for k, i in enumerate(items))
    prompt = PROMPT.format(facts=facts(tl), texts=texts or "(no text found)", question=question.strip())
    r = llm.chat(prompt, images=[str(T._abspath(image_path or path))], backend=backend, max_tokens=300,
                 json_schema=SCHEMA, cache=True)
    trace = [f"text layer: {len(tl.items)} texts in {tl.tiles} tile(s); {facts(tl).splitlines()[0]}"]
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
    ev = [Evidence(file=image_path or path, page=0, bbox=[round(x, 1) for x in i.box], bbox_space="image_px",
                   note=f"text '{i.text[:60]}'") for i in cited[:6]]
    # Confidence: a prior guess, not yet calibrated (experiments/w3/textlayer_eval.py, scan probes)
    conf = 0.7 if (cited and in_cited) else 0.5 if cited else 0.3
    missing = [] if cited else ["the answer is not printed as text: an image-only reading"]
    assumptions = [a for a in [str(d.get("assumptions", "")).strip()] if a and a.lower() not in ("none", "n/a")]
    trace.append(f"answer '{val}' from text lines {[k for k in d.get('lines', [])][:8]}"
                 + (" (literal match)" if in_cited else ""))
    return Answer(value=value, unit=unit, confidence=conf, evidence=ev, solver=solver, trace=trace,
                  assumptions=assumptions, missing=missing)
