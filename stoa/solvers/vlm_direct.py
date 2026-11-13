"""vlm_direct — the "just ask a VLM" baseline every other solver must beat (owner: R2).

Render the drawing (PNG/JPEG as is, PDF page -> PNG with PyMuPDF), ask the question, parse one value.
IFC files are not handled (abstain), unless a sibling PDF/PNG of the same drawing exists.

Options (pass via the eval tool's solver kwargs, e.g. `--solver vlm_direct -k backend=nvidia`):
  backend      "local" (default, shared vLLM on :8001) or "nvidia" (hosted Nemotron; rate-limited)
  model        override the backend's default model id
  max_pixels   image budget (default 3.2 Mpx)
  dpi          PDF render dpi before downscaling (default 150)
  ground       count questions only: "box" (or 1) -> ask for one box per counted object, "point" -> one point
               per object (cheaper); the boxes/points become evidence and, with count_from=list (default),
               the answer is the number of (de-duplicated) items; count_from=stated keeps the stated count
  samples      N > 1 -> self-consistency: N samples at temperature 0.7 in one request (image encoded once),
               answer = most common value, confidence = its vote share (direct style only)
  min_pixels   upscale small images to at least this many pixels before sending (default 0 = never)
  with_text    1 -> append the PDF's text layer (words, reading order) to the prompt (PDF only)
  thinking     1 -> let hybrid-thinking models think (slower)
  style        "direct" (default: answer only, ~10 output tokens, cheapest) or "cot" (reason step by step,
               then `ANSWER: x`; up to max_tokens; if it runs out of tokens a short follow-up asks for the answer)
"""

from __future__ import annotations

import re
from pathlib import Path

from stoa.contract import Answer, Evidence
from stoa.solvers import register
from stoa.solvers.base import BaseSolver

IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")

SYSTEM = (
    "You are an expert architect and quantity surveyor. You read floor plans and construction drawings "
    "precisely. Answer the question about the drawing exactly as asked."
)

_COUNT = re.compile(
    r"\b(how many|number of|count|kuinka monta|montako|wie viele|anzahl|combien|nombre de|cuántos|cuántas|"
    r"número de|quanti|quante|hvor mange|hur många|hoeveel|ile|kui palju|mitu|antal)\b", re.I)
_VOLUME = re.compile(r"(m³|m3\b|cubic|volume|volumen|nettovolumen|tilavuus|maht)", re.I)
_AREA = re.compile(r"(m²|m2\b|ft²|ft2\b|sq\.? ?ft|square|area|fläche|pinta-ala|ala\b|surface|superficie|"
                   r"pind|areal)", re.I)
_LENGTH = re.compile(r"(\bin met(re|er)s?\b|\bmeters?\b|\bmetres?\b|\blength\b|\blänge\b|\blængde\b|"
                     r"\bpituus\b|\blong\b|\bm\)\?)", re.I)


def infer_kind(question: str) -> tuple[str, str | None]:
    """-> (type, unit): ('count','count') | ('area','m2'|'ft2') | ('volume','m3') | ('length','m') | ('text',None)."""
    q = question
    if _VOLUME.search(q):
        return "volume", "m3"
    if _AREA.search(q) and not _COUNT.search(q):
        return "area", ("ft2" if re.search(r"ft²|ft2|sq\.? ?ft|square feet", q, re.I) else "m2")
    if _COUNT.search(q):
        return "count", "count"
    if _LENGTH.search(q):
        return "length", "m"
    if _AREA.search(q):
        return "area", "m2"
    return "text", None


_NUM = re.compile(r"-?\d[\d\s  ']*(?:[.,]\d+)?")


def parse_number(text: str, integer: bool) -> float | int | None:
    """The answer number: prefer `answer: X` / JSON "answer", else the LAST number in the text."""
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r'"?(?:answer|final answer|value)"?\s*[:=]\s*(-?[\d.,\s ]+)', t, re.I)
    cands = [m.group(1)] if m else _NUM.findall(t)
    for raw in ([cands[0]] if m else reversed(cands)):
        s = raw.strip().replace(" ", "").replace(" ", "").replace("'", "").replace(" ", "")
        if not s or not re.search(r"\d", s):
            continue
        if "," in s and "." in s:  # 1,234.5 or 1.234,5
            s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
        elif "," in s:
            parts = s.split(",")
            s = s.replace(",", "") if (len(parts) == 2 and len(parts[1]) == 3 and integer) else s.replace(",", ".")
        try:
            v = float(s.rstrip("."))
        except ValueError:
            continue
        return int(round(v)) if integer else v
    return None


FORMAT = {
    "count": "Count carefully. Reply with the final count as a single integer on the last line, like `ANSWER: 7`.",
    "area": "Reply with the final value in {unit} as a number on the last line, like `ANSWER: 42.5`.",
    "volume": "Reply with the final value in m³ as a number on the last line, like `ANSWER: 12.3`.",
    "length": "Reply with the final value in metres as a number on the last line, like `ANSWER: 25.4`.",
    "text": "Answer briefly and precisely on the last line, like `ANSWER: <your answer>`.",
}

DIRECT = {
    "count": "Reply with only the final count as a single integer, nothing else.",
    "area": "Reply with only the final value in {unit} as a number, nothing else.",
    "volume": "Reply with only the final value in m³ as a number, nothing else.",
    "length": "Reply with only the final value in metres as a number, nothing else.",
    "text": "Reply with only the answer, as briefly as possible.",
}

GROUND = {
    "box": ("Locate every object that the question asks to count. Output a JSON list with one entry per object: "
            '[{"bbox_2d": [x1, y1, x2, y2], "label": "<object>"}] (coordinates 0-1000 relative to the image). '
            "Output [] if there are none. Then give the final count on the last line like `ANSWER: 7`."),
    "point": ("Point to every object that the question asks to count. Output a JSON list with one entry per "
              'object: [{"point_2d": [x, y], "label": "<object>"}] (coordinates 0-1000 relative to the image). '
              "Output [] if there are none. Then give the final count on the last line like `ANSWER: 7`."),
}


@register("vlm_direct")
class VlmDirect(BaseSolver):
    extensions = (*IMG_EXT, ".pdf", ".ifc")

    def __init__(self, backend: str = "local", model: str | None = None, max_pixels: int | str = 3_200_000,
                 dpi: int | str = 150, ground: int | str = 0, with_text: int | str = 0, thinking: int | str = 0,
                 max_tokens: int | str = 1024, style: str = "direct", count_from: str = "list",
                 min_pixels: int | str = 0, samples: int | str = 1, **kwargs):
        super().__init__(**kwargs)
        self.backend = backend
        self.model = model
        self.max_pixels = int(max_pixels)
        self.dpi = int(dpi)
        g = str(ground).lower()
        self.ground = {"0": "", "": "", "false": "", "1": "box", "box": "box", "point": "point"}[g]
        self.count_from = count_from
        self.min_pixels = int(min_pixels)
        self.samples = int(samples)
        self.with_text = bool(int(with_text))
        self.thinking = bool(int(thinking))
        self.style = style
        self.max_tokens = int(max_tokens) if not self.thinking else max(int(max_tokens), 4096)

    # -- input --------------------------------------------------------------------------------
    def _pick_file(self, path: str) -> str | None:
        ext = Path(path).suffix.lower()
        if ext in IMG_EXT or ext == ".pdf":
            return path
        sib = self.siblings(path)  # same drawing in other formats: {".pdf": "data/..", ...}
        for e in (".pdf", ".png", ".jpg", ".jpeg"):
            if e in sib:
                return sib[e]
        return None

    @staticmethod
    def _pick_page(doc, question: str) -> int:
        """For multi-page PDFs: the page whose text mentions the sheet id in the question, else page 0."""
        if len(doc) == 1:
            return 0
        m = re.search(r"\bsheet\s+([A-Z]{1,3}-?\d{1,4}(?:\.\d+)?)", question, re.I)
        if m:
            sid = m.group(1).upper()
            for i, pg in enumerate(doc):
                if sid in pg.get_text().upper():
                    return i
        return 0

    def solve(self, path: str, question: str) -> Answer:
        from stoa import llm

        with llm.cost_meter() as cost:
            ans = self._solve(path, question)
        ans.trace.append(str(cost))  # the eval's CostMeter gets the same numbers via stoa.llm -> record_cost
        return ans

    def _solve(self, path: str, question: str) -> Answer:
        from stoa import llm

        trace: list[str] = []
        use = self._pick_file(path)
        if use is None:
            return self.abstain("no raster/PDF version of this drawing (IFC-only)", trace)
        if use != path:
            trace.append(f"using sibling {use}")
        kind, unit = infer_kind(question)
        trace.append(f"kind={kind} unit={unit}")

        ap = self.abspath(use)
        page = None
        px_per_pt = None
        text_layer = ""
        if ap.suffix.lower() == ".pdf":
            import pymupdf

            with pymupdf.open(ap) as doc:
                page = self._pick_page(doc, question)
                if self.with_text:
                    text_layer = doc[page].get_text()[:6000]
            img, px_per_pt = llm.render_pdf_page(ap, page, dpi=self.dpi)
            trace.append(f"rendered page {page} at {self.dpi} dpi -> {img.width}x{img.height}")
        else:
            img = llm.load_image(ap)
        up = 1.0
        if self.min_pixels and img.width * img.height < self.min_pixels:
            up = min((self.min_pixels / (img.width * img.height)) ** 0.5, 4.0)
            img = img.resize((round(img.width * up), round(img.height * up)), resample=3)
            up = img.width / (img.width / up)
            trace.append(f"upscaled x{up:.2f} -> {img.width}x{img.height}")

        direct = self.style == "direct" and not self.ground and not self.thinking
        fmt = (DIRECT if direct else FORMAT)[kind].format(unit="ft²" if unit == "ft2" else "m²")
        prompt = question.strip()
        if text_layer:
            prompt += "\n\nText found on the drawing (PDF text layer, reading order):\n" + text_layer
        grounded = bool(self.ground) and kind == "count"
        prompt += "\n\n" + (GROUND[self.ground] if grounded else fmt)

        try:
            r = llm.chat(prompt, images=[img], system=SYSTEM, backend=self.backend, model=self.model,
                         max_tokens=(64 if direct and kind != "text" else 256 if direct else
                                     max(self.max_tokens, 2048) if grounded else self.max_tokens),
                         thinking=self.thinking, max_pixels=self.max_pixels,
                         **({"n": self.samples, "temperature": 0.7} if (direct and self.samples > 1) else {}))
            if r.finish_reason == "length" and not direct and "ANSWER:" not in r.text:
                # rambling/looping CoT: ask for the answer only, keeping what it saw so far
                trace.append("cot hit max_tokens; asking for the final answer")
                msgs = [{"role": "user", "content": prompt},
                        {"role": "assistant", "content": r.text[-3000:]},
                        {"role": "user", "content": DIRECT[kind].format(unit="ft²" if unit == "ft2" else "m²")}]
                r2 = llm.chat(msgs, images=[img], system=SYSTEM, backend=self.backend, model=self.model,
                              max_tokens=64, thinking=False, max_pixels=self.max_pixels)
                r = r2
        except Exception as e:  # noqa: BLE001
            return self.abstain(f"llm error: {type(e).__name__}: {str(e)[:200]}", trace)
        trace.append(f"{r.backend}:{r.model} {r.latency_s:.1f}s tok {r.prompt_tokens}->{r.completion_tokens}")
        out = r.text.strip()
        trace.append("raw: " + out[-300:].replace("\n", " | "))

        evidence: list[Evidence] = []
        items: list[list[float]] = []
        if grounded:
            body = out.split("ANSWER:")[0]
            if self.ground == "point":
                pts = llm.parse_points(body, r.images[0])
                pts = llm.nms_points(pts, min_dist=0.004 * max(img.width, img.height))
                items = [[p.x, p.y, p.x, p.y] for p in pts]
                labels = [p.label for p in pts]
            else:
                bxs = llm.nms_boxes(llm.parse_boxes(body, r.images[0]), iou_thr=0.7)
                items = [b.as_list() for b in bxs]
                labels = [b.label for b in bxs]
            for i, (bb, lab) in enumerate(zip(items, labels)):
                bb = [v / up for v in bb]  # back to the file's own pixels
                if px_per_pt:  # rendered PDF -> PDF points
                    evidence.append(Evidence(file=use, page=page, bbox=[v / px_per_pt for v in bb],
                                             bbox_space="pdf_pt", note=f"{lab or 'item'} {i + 1}"))
                else:
                    evidence.append(Evidence(file=use, bbox=bb, bbox_space="image_px",
                                             note=f"{lab or 'item'} {i + 1}"))
            trace.append(f"{len(items)} {self.ground}es" if self.ground == "box" else f"{len(items)} points")

        last = out.splitlines()[-1] if out else ""
        if kind == "text":
            m = re.search(r"ANSWER:\s*(.+)", out, re.S)
            value = (m.group(1).strip() if m else out).strip("` ")[:500]
            return Answer(value=value or None, unit=None, confidence=0.2, evidence=evidence, trace=trace,
                          solver=self.name)

        conf = 0.3
        if direct and self.samples > 1 and len(r.texts) > 1:
            import collections

            vals = [parse_number(t, integer=(kind == "count")) for t in r.texts]
            vals = [v for v in vals if v is not None]
            if vals:
                if kind == "count":
                    best, votes = collections.Counter(vals).most_common(1)[0]
                else:  # continuous: median is the robust vote
                    best = sorted(vals)[len(vals) // 2]
                    votes = sum(1 for v in vals if abs(v - best) <= 0.02 * max(abs(best), 1e-9))
                conf = votes / len(r.texts)
                trace.append(f"samples {vals} -> {best} ({votes}/{len(r.texts)})")
                return Answer(value=best, unit=unit, confidence=round(conf, 3), evidence=evidence, trace=trace,
                              solver=self.name)
        m = re.search(r"ANSWER:\s*([^\n]+)", out)
        value = parse_number(m.group(1) if m else (last or out), integer=(kind == "count"))
        if value is None:
            value = parse_number(out, integer=(kind == "count"))
        if grounded and value is not None and len(items) != value:
            trace.append(f"stated {value} vs {len(items)} located")
        if grounded and self.count_from == "list" and (items or re.search(r"\[\s*\]", out)):
            value = len(items)
        if value is None:
            return self.abstain("could not parse a number", trace)
        return Answer(value=value, unit=unit, confidence=0.3, evidence=evidence, trace=trace, solver=self.name)
