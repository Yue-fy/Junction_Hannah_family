"""vlm_direct — the "just ask a VLM" baseline every other solver must beat (owner: R2).

Render the drawing (PNG/JPEG as is, PDF page -> PNG with PyMuPDF), ask the question, parse one value.
IFC files are not handled (abstain), unless a sibling PDF/PNG of the same drawing exists.

Options (pass via the eval tool's solver kwargs, e.g. `--solver vlm_direct -k backend=nvidia`):
  backend      "local" (default, shared vLLM on :8001) or "nvidia" (hosted Nemotron; rate-limited)
  model        override the backend's default model id
  max_pixels   image budget (default 3.2 Mpx)
  dpi          PDF render dpi before downscaling (default 150)
  ground       1 -> for count questions also ask for one box per counted object; the boxes become evidence
               (and the count is the number of boxes when the model gives both and they disagree: see `trust`)
  with_text    1 -> append the PDF's text layer (words, reading order) to the prompt (PDF only)
  thinking     1 -> let hybrid-thinking models think (slower)
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

GROUND = ("First list every object you count as JSON, one entry per object: "
          '[{"bbox_2d": [x1, y1, x2, y2], "label": "<object>"}] (coordinates 0-1000 relative to the image). '
          "Then give the final count on the last line like `ANSWER: 7`.")


@register("vlm_direct")
class VlmDirect(BaseSolver):
    extensions = (*IMG_EXT, ".pdf", ".ifc")

    def __init__(self, backend: str = "local", model: str | None = None, max_pixels: int | str = 3_200_000,
                 dpi: int | str = 150, ground: int | str = 0, with_text: int | str = 0, thinking: int | str = 0,
                 max_tokens: int | str = 1024, **kwargs):
        super().__init__(**kwargs)
        self.backend = backend
        self.model = model
        self.max_pixels = int(max_pixels)
        self.dpi = int(dpi)
        self.ground = bool(int(ground))
        self.with_text = bool(int(with_text))
        self.thinking = bool(int(thinking))
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
        ans.trace.append(str(cost))
        if "cost" in Answer.model_fields:  # contract addition (Stoa feedback); additive
            ans.cost = {**cost.as_dict(), **(ans.cost or {})}  # type: ignore[attr-defined]
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

        fmt = FORMAT[kind].format(unit="ft²" if unit == "ft2" else "m²")
        prompt = question.strip()
        if text_layer:
            prompt += "\n\nText found on the drawing (PDF text layer, reading order):\n" + text_layer
        prompt += "\n\n" + (GROUND if (self.ground and kind == "count") else fmt)

        try:
            r = llm.chat(prompt, images=[img], system=SYSTEM, backend=self.backend, model=self.model,
                         max_tokens=self.max_tokens, thinking=self.thinking, max_pixels=self.max_pixels)
        except Exception as e:  # noqa: BLE001
            return self.abstain(f"llm error: {type(e).__name__}: {str(e)[:200]}", trace)
        trace.append(f"{r.backend}:{r.model} {r.latency_s:.1f}s tok {r.prompt_tokens}->{r.completion_tokens}")
        out = r.text.strip()
        trace.append("raw: " + out[-300:].replace("\n", " | "))

        evidence: list[Evidence] = []
        if self.ground and kind == "count":
            boxes = llm.parse_boxes(out, r.images[0])
            for i, b in enumerate(boxes):
                bb = b.as_list()
                if px_per_pt:  # rendered PDF -> PDF points
                    evidence.append(Evidence(file=use, page=page, bbox=[v / px_per_pt for v in bb],
                                             bbox_space="pdf_pt", note=f"{b.label or 'item'} {i + 1}"))
                else:
                    evidence.append(Evidence(file=use, bbox=bb, bbox_space="image_px",
                                             note=f"{b.label or 'item'} {i + 1}"))
            trace.append(f"{len(boxes)} boxes")

        last = out.splitlines()[-1] if out else ""
        if kind == "text":
            m = re.search(r"ANSWER:\s*(.+)", out, re.S)
            value = (m.group(1).strip() if m else out).strip("` ")
            return Answer(value=value or None, unit=None, confidence=0.2, evidence=evidence, trace=trace,
                          solver=self.name)

        m = re.search(r"ANSWER:\s*([^\n]+)", out)
        value = parse_number(m.group(1) if m else (last or out), integer=(kind == "count"))
        if value is None:
            value = parse_number(out, integer=(kind == "count"))
        if value is None:
            return self.abstain("could not parse a number", trace)
        if self.ground and kind == "count" and evidence and len(evidence) != value:
            trace.append(f"stated {value} vs {len(evidence)} boxes")
        return Answer(value=value, unit=unit, confidence=0.3, evidence=evidence, trace=trace, solver=self.name)
