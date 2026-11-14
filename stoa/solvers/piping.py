"""Deterministic question answering for vector construction piping plans."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import json
import math
import os
import re
import threading

from openai import OpenAIError
import pymupdf
from PIL import Image

from stoa import llm
from stoa.contract import Answer, Evidence
from stoa.solvers import register
from stoa.solvers.base import BaseSolver


_TAG_RE = re.compile(
    r"(?<![A-Z0-9])(?:(FSCV|FSI|FSR|CV|FP|PS)\s*[-–—]\s*(\d+)|(PG|MAV))(?![A-Z0-9])",
    re.IGNORECASE,
)
_SIZE_RE = re.compile(
    r"(?<![A-Z0-9_./-])"
    r"(?P<size>(?:\d+(?:\s*-\s*|\s+)\d+/\d+|\d+\.\d+|\d+/\d+|\d+))"
    r"\s*[\"“”″](?![A-Z0-9_])",
    re.IGNORECASE,
)
_SHEET_RE = re.compile(r"\b(?:SHEET\s+)?(M(?:S|H)?-?\d{3}[A-Z]?)\b", re.IGNORECASE)


def parse_tags(text: str) -> list[str]:
    """Return canonical piping tags in reading order."""
    return [_canonical_tag(match) for match in _TAG_RE.finditer(text)]


def _canonical_tag(match: re.Match[str]) -> str:
    if match.group(3):
        return match.group(3).upper()
    return f"{match.group(1).upper()}-{int(match.group(2))}"


def parse_sizes(text: str) -> list[str]:
    """Return normalized whole, decimal, or fractional inch sizes in reading order."""
    sizes: list[str] = []
    for match in _SIZE_RE.finditer(text):
        value = re.sub(r"\s*-\s*", " ", match.group("size"))
        sizes.append(re.sub(r"\s+", " ", value).strip() + '"')
    return sizes


@dataclass(frozen=True)
class _Word:
    text: str
    bbox: tuple[float, float, float, float]
    block: int
    line: int
    order: int


@dataclass(frozen=True)
class _Block:
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class _Page:
    number: int
    text: str
    words: tuple[_Word, ...]
    blocks: tuple[_Block, ...]


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _augment_adjacent_blocks(blocks: tuple[_Block, ...]) -> tuple[_Block, ...]:
    """Keep source blocks and add pairs split by PDF text extraction."""
    combined: list[_Block] = list(blocks)
    for index, first in enumerate(blocks):
        ax0, ay0, ax1, ay1 = first.bbox
        for second in blocks[index + 1:]:
            bx0, by0, bx1, by1 = second.bbox
            horizontal_gap = max(bx0 - ax1, ax0 - bx1)
            vertical_overlap = _overlap(ay0, ay1, by0, by1)
            min_height = min(ay1 - ay0, by1 - by0)
            if 0 <= horizontal_gap <= 8 and min_height > 0 and vertical_overlap / min_height >= 0.65:
                left, right = (first, second) if ax0 <= bx0 else (second, first)
                combined.append(
                    _Block(
                        text=f"{left.text} {right.text}",
                        bbox=(min(ax0, bx0), min(ay0, by0), max(ax1, bx1), max(ay1, by1)),
                    )
                )
    return tuple(combined)


_PDF_LOCKS: dict[str, threading.Lock] = {}
_PDF_LOCKS_GUARD = threading.Lock()


@lru_cache(maxsize=16)
def _read_pdf_cached(path: str, _mtime_ns: int, _size: int) -> tuple[_Page, ...]:
    pages: list[_Page] = []
    with pymupdf.open(path) as document:
        for page_number, page in enumerate(document):
            words = tuple(
                _Word(
                    text=str(raw[4]),
                    bbox=tuple(float(value) for value in raw[:4]),
                    block=int(raw[5]),
                    line=int(raw[6]),
                    order=int(raw[7]),
                )
                for raw in page.get_text("words", sort=True)
            )
            source_blocks = tuple(
                _Block(
                    text=" ".join(str(raw[4]).split()),
                    bbox=tuple(float(value) for value in raw[:4]),
                )
                for raw in page.get_text("blocks", sort=True)
                if str(raw[4]).strip()
            )
            blocks = _augment_adjacent_blocks(source_blocks)
            pages.append(_Page(page_number, page.get_text(), words, blocks))
    return tuple(pages)


def _read_pdf(path: str) -> tuple[_Page, ...]:
    resolved = str(Path(path).resolve())
    with _PDF_LOCKS_GUARD:
        lock = _PDF_LOCKS.setdefault(resolved, threading.Lock())
    with lock:
        stat = Path(resolved).stat()
        return _read_pdf_cached(resolved, stat.st_mtime_ns, stat.st_size)


def _normal_sheet(value: str) -> str:
    return value.upper().replace("-", "")


def _select_page(pages: tuple[_Page, ...], question: str) -> _Page | None:
    sheet_match = _SHEET_RE.search(question)
    if sheet_match:
        wanted = _normal_sheet(sheet_match.group(1))
        candidates: list[tuple[int, _Page]] = []
        for page in pages:
            if not any(_normal_sheet(found) == wanted for found in _SHEET_RE.findall(page.text)):
                continue
            score = 0
            for block in page.blocks:
                block_sheets = [_normal_sheet(found) for found in _SHEET_RE.findall(block.text)]
                compact = _normal_sheet(block.text.strip())
                if compact == wanted:
                    score = max(score, 100)
                elif block_sheets == [wanted] and compact.startswith(wanted):
                    score = max(score, 50)
            candidates.append((score, page))
        return max(candidates, key=lambda item: (item[0], item[1].number))[1] if candidates else None
    if not pages:
        return None
    return max(pages, key=lambda page: len(_word_tags(page)))


def _line_word_spans(page: _Page) -> list[tuple[str, list[tuple[int, int, _Word]]]]:
    grouped: dict[tuple[int, int], list[_Word]] = {}
    for word in page.words:
        grouped.setdefault((word.block, word.line), []).append(word)

    lines: list[tuple[str, list[tuple[int, int, _Word]]]] = []
    for words in grouped.values():
        parts: list[str] = []
        spans: list[tuple[int, int, _Word]] = []
        cursor = 0
        for word in sorted(words, key=lambda item: item.order):
            if parts:
                cursor += 1
            start = cursor
            parts.append(word.text)
            cursor += len(word.text)
            spans.append((start, cursor, word))
        lines.append((" ".join(parts), spans))
    return lines


def _matched_word(match: re.Match[str], spans: list[tuple[int, int, _Word]]) -> _Word:
    members = [word for start, end, word in spans if start < match.end() and end > match.start()]
    first = members[0]
    return _Word(
        text=match.group(0),
        bbox=(
            min(word.bbox[0] for word in members),
            min(word.bbox[1] for word in members),
            max(word.bbox[2] for word in members),
            max(word.bbox[3] for word in members),
        ),
        block=first.block,
        line=first.line,
        order=first.order,
    )


def _word_tags(page: _Page) -> list[tuple[str, _Word]]:
    found: list[tuple[str, _Word]] = []
    for text, spans in _line_word_spans(page):
        for match in _TAG_RE.finditer(text):
            found.append((_canonical_tag(match), _matched_word(match, spans)))
    return found


_BARE_PS_RE = re.compile(r"(?<![A-Z0-9])PS(?!\s*[-–—]\s*\d)(?![A-Z0-9])", re.IGNORECASE)


def _bare_ps_words(page: _Page) -> list[_Word]:
    return [
        _matched_word(match, spans)
        for text, spans in _line_word_spans(page)
        for match in _BARE_PS_RE.finditer(text)
    ]


def _count_target(question: str) -> tuple[str, bool] | None:
    q = question.upper()
    distinct = "DISTINCT" in q or "DIFFERENT" in q or "UNIQUE" in q
    if "PRESSURE" in q and ("SENSOR" in q or "GAUGE" in q):
        return ("PS" if "SENSOR" in q else "PG", distinct)
    if "MANUAL AIR VENT" in q or re.search(r"\bMAV\b", q):
        return "MAV", distinct
    for family in ("FSCV", "FSI", "FSR", "CV", "FP"):
        if re.search(rf"\b{family}(?:-|\b)", q):
            return family, distinct
    if "PIPE-SUPPORT" in q or "PIPE SUPPORT" in q or "PS-N" in q or re.search(r"\bPS-\d", q):
        return "PS-", distinct
    return None


def _evidence(path: str, page: _Page, tag: str, word: _Word) -> Evidence:
    return Evidence(
        file=path,
        page=page.number,
        bbox=list(word.bbox),
        bbox_space="pdf_pt",
        note=tag,
    )


def _block_evidence(path: str, page: _Page, block: _Block) -> Evidence:
    return Evidence(
        file=path,
        page=page.number,
        bbox=list(block.bbox),
        bbox_space="pdf_pt",
        note=block.text[:180],
    )


_STOPWORDS = {
    "a", "according", "and", "are", "come", "comes", "connect", "connected", "does", "from", "go",
    "goes", "how", "in", "inch", "inches", "is", "it", "labeled", "line", "m", "many", "material",
    "of", "on", "pipe", "plan", "sheet", "shown", "size", "the", "to", "what", "where", "which",
}
_GENERIC_TOKENS = {"connection", "cross", "discharge", "header", "return"}


def _tokens(text: str) -> set[str]:
    normalized = re.sub(r"\bF\s*/\s*S\b", "filter separator", text, flags=re.IGNORECASE)
    normalized = re.sub(r"\bSS\b", "stainless steel", normalized, flags=re.IGNORECASE)
    normalized = _SHEET_RE.sub(" ", normalized)
    return {token for token in re.findall(r"[a-z0-9]+", normalized.lower()) if token not in _STOPWORDS}


def _rank_blocks(page: _Page, question: str) -> list[tuple[float, int, _Block]]:
    query = _tokens(question)
    note_match = re.search(r"\bNOTE\s+(\d+)\b", question, re.IGNORECASE)
    ranked: list[tuple[float, int, _Block]] = []
    for index, block in enumerate(page.blocks):
        block_tokens = _tokens(block.text)
        overlap = query & block_tokens
        exact_note = bool(note_match and re.match(rf"\s*{note_match.group(1)}\s*[.)]", block.text))
        if not overlap and not exact_note:
            continue
        score = float(sum(1 if token in _GENERIC_TOKENS else 3 for token in overlap))
        score -= 0.05 * len(block_tokens - query)
        if exact_note:
            score += 8.0
        if parse_sizes(block.text) and re.search(r"\b(?:SIZE|DIAMETER|HEADER|LINE)\b", question, re.IGNORECASE):
            score += 2.0
        if re.search(r"\bFROM\b", question, re.IGNORECASE) and re.search(r"\bFROM\b", block.text, re.IGNORECASE):
            score += 2.0
        if re.search(r"\bTO\b", question, re.IGNORECASE) and re.search(r"\bTO\b", block.text, re.IGNORECASE):
            score += 2.0
        if score > 0:
            ranked.append((score, index, block))
    return sorted(ranked, key=lambda item: (-item[0], item[1]))


def _human_inches(value: str) -> str:
    return f"{value[:-1]} inches"


def _size_answer(path: str, page: _Page, question: str) -> Answer | None:
    ranked = _rank_blocks(page, question)
    if not ranked:
        return None
    _, _, block = ranked[0]
    sizes = parse_sizes(block.text)
    if not sizes:
        return None
    if "MATERIAL" in question.upper() or "STAINLESS" in question.upper():
        material = "stainless steel" if re.search(r"\bSS\b", block.text, re.IGNORECASE) else None
        if material:
            value = f"{sizes[0][:-1]}-inch {material}"
        else:
            value = _human_inches(sizes[0])
    elif len(sizes) >= 2 and re.search(r"\b(?:REDUCER|INCREASER|SIZES)\b", question, re.IGNORECASE):
        value = f"{sizes[0][:-1]} inches by {sizes[1][:-1]} inches"
    else:
        value = _human_inches(sizes[0])
    return Answer(
        value=value,
        confidence=0.95,
        evidence=[_block_evidence(path, page, block)],
        trace=[f"selected PDF page {page.number}", "ranked named piping callouts", f"read size from: {block.text[:100]}"],
        solver="piping",
    )


def _note_answer(path: str, page: _Page, question: str) -> Answer | None:
    ranked = _rank_blocks(page, question)
    if not ranked:
        return None
    _, _, block = ranked[0]
    ufc = re.search(r"\bUFC\s+\d+-\d+-\d+\b", block.text, re.IGNORECASE)
    if ufc:
        value = ufc.group(0).upper()
    elif "LARGE FILLED DOT" in block.text.upper():
        sheet = re.search(r"\bS-\d+\b", block.text, re.IGNORECASE)
        value = f"Pipe-support locations; see sheet {sheet.group(0).upper()}" if sheet else "Pipe-support locations"
    else:
        value = re.sub(r"^\s*\d+\s*[.)]\s*", "", block.text).rstrip(" .")
    return Answer(
        value=value,
        confidence=0.97,
        evidence=[_block_evidence(path, page, block)],
        trace=[f"selected PDF page {page.number}", "matched the requested designer note", f"read: {block.text[:120]}"],
        solver="piping",
    )


def _connection_value(text: str, question: str) -> str | None:
    direction = "FROM" if re.search(r"\b(?:FROM|COME\s+FROM)\b", question, re.IGNORECASE) else "TO"
    match = re.search(rf"\b{direction}\s+(.+)", text, re.IGNORECASE)
    if not match:
        return None
    value = re.split(r"\b(?:SEE|DETAIL|NOTE)\b", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.sub(r"\s+", " ", value).strip(" ,.;()")
    return value.lower().capitalize() if value else None


def _render_crop(pdf_path: Path, page_number: int, blocks: list[_Block]) -> Image.Image:
    with pymupdf.open(pdf_path) as document:
        page = document[page_number]
        if blocks:
            raw = pymupdf.Rect(blocks[0].bbox)
            for block in blocks[1:]:
                raw |= pymupdf.Rect(block.bbox)
            clip = raw * page.rotation_matrix
            clip = pymupdf.Rect(clip.x0 - 144, clip.y0 - 144, clip.x1 + 144, clip.y1 + 144) & page.rect
        else:
            clip = page.rect
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), clip=clip, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _gemini_connection(path: str, resolved: Path, page: _Page, question: str) -> Answer | None:
    if not os.environ.get("GEMINI_API_KEY") or llm.gemini_calls_today() >= 60:
        return None
    ranked = _rank_blocks(page, question)[:12]
    if not ranked:
        return None
    candidates = [
        {"id": f"b{index}", "text": block.text, "bbox": [round(value, 2) for value in block.bbox]}
        for _, index, block in ranked
    ]
    prompt = (
        "Answer the piping connection question using only the labeled drawing items below and the crop. "
        "Return a concise value and cite only listed item IDs.\n"
        f"QUESTION: {question}\nITEMS: {json.dumps(candidates, ensure_ascii=False)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["value", "evidence_ids", "confidence"],
        "additionalProperties": False,
    }
    by_id = {f"b{index}": block for _, index, block in ranked}
    try:
        crop = _render_crop(resolved, page.number, [block for _, _, block in ranked[:4]])
        result = llm.chat(
            prompt,
            images=[crop],
            backend="gemini",
            model="gemini-3.1-pro-preview",
            system="Use only visible piping labels; never infer an unlabeled connection.",
            json_schema=schema,
            max_tokens=512,
            thinking=True,
            retries=0,
            purpose="piping relational connection question",
        )
        payload = llm.extract_json(result.text)
    except (OpenAIError, KeyError, TypeError, ValueError, RuntimeError, OSError, IndexError):
        return None

    if not isinstance(payload, dict) or set(payload) != {"value", "evidence_ids", "confidence"}:
        return None
    raw_value = payload["value"]
    raw_ids = payload["evidence_ids"]
    raw_confidence = payload["confidence"]
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    if (
        not isinstance(raw_ids, list)
        or not raw_ids
        or not all(isinstance(item, str) and item in by_id for item in raw_ids)
    ):
        return None
    if (
        isinstance(raw_confidence, bool)
        or not isinstance(raw_confidence, (int, float))
        or not math.isfinite(raw_confidence)
        or not 0 <= raw_confidence <= 1
    ):
        return None
    value = raw_value.strip()
    ids = raw_ids
    confidence = float(raw_confidence)
    return Answer(
        value=value,
        confidence=confidence,
        evidence=[_block_evidence(path, page, by_id[item]) for item in ids],
        trace=[f"selected PDF page {page.number}", "sent structured labels and a focused crop to Gemini 3.1 Pro", "validated cited item IDs"],
        solver="piping",
    )


def _connection_answer(path: str, resolved: Path, page: _Page, question: str) -> Answer | None:
    gemini = _gemini_connection(path, resolved, page, question)
    if gemini is not None:
        return gemini
    ranked = _rank_blocks(page, question)
    for _, _, block in ranked:
        value = _connection_value(block.text, question)
        if value:
            return Answer(
                value=value,
                confidence=0.78,
                evidence=[_block_evidence(path, page, block)],
                trace=[f"selected PDF page {page.number}", "used keyless deterministic fallback", f"read labeled connection: {block.text[:120]}"],
                solver="piping",
                assumptions=["the printed FROM/TO callout names the requested connection"],
                missing=[] if os.environ.get("GEMINI_API_KEY") else ["GEMINI_API_KEY unavailable; crop reasoning was skipped"],
            )
    return None


def _fraction(value: str) -> float:
    if "/" not in value:
        return float(value)
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def _points_per_foot(text: str) -> float | None:
    match = re.search(r"SCALE\s*:\s*(\d+(?:/\d+)?)\s*[\"”]\s*=\s*(\d+)\s*['’]", text, re.IGNORECASE)
    if not match:
        return None
    return 72.0 * _fraction(match.group(1)) / float(match.group(2))


def _measurement_answer(path: str, page: _Page, question: str) -> Answer | None:
    requested = re.findall(r"\b(?:FSCV|FSI|FSR|CV|FP|PS)-\d+\b", question.upper())
    if len(requested) < 2:
        return None
    located: list[tuple[str, _Word]] = []
    all_tags = _word_tags(page)
    for tag in requested[:2]:
        match = next(((found, word) for found, word in all_tags if found == tag), None)
        if match is None:
            return None
        located.append(match)
    points_per_foot = _points_per_foot(page.text)
    if not points_per_foot:
        return None
    centers = [((word.bbox[0] + word.bbox[2]) / 2, (word.bbox[1] + word.bbox[3]) / 2) for _, word in located]
    distance_points = math.dist(centers[0], centers[1])
    feet = round((distance_points / points_per_foot) * 2) / 2
    return Answer(
        value=f"{feet:g} ft",
        confidence=0.82,
        evidence=[_evidence(path, page, tag, word) for tag, word in located],
        trace=[f"selected PDF page {page.number}", f"parsed scale: {points_per_foot:g} PDF points per foot", f"measured tag-center span: {distance_points:.2f} PDF points"],
        solver="piping",
        assumptions=["the tagged branch centerlines define a straight header segment in plan view"],
    )


@register("piping")
class PipingSolver(BaseSolver):
    extensions = (".pdf",)

    _CUES = re.compile(
        r"\b(?:PIP(?:E|ING)|VALVE|PUMP|HEADER|VENT|PRESSURE\s+(?:GAUGE|SENSOR)|"
        r"SUCTION|HYDRANT|TANK|FSCV|FSI|FSR|CV-\d|FP-\d|PS-\d|PG|MAV)\b",
        re.IGNORECASE,
    )

    def can_handle(self, path: str, question: str) -> bool:
        return Path(path).suffix.lower() == ".pdf" and bool(self._CUES.search(question) or _SHEET_RE.search(question))

    def solve(self, path: str, question: str) -> Answer:
        if not self.can_handle(path, question):
            return self.abstain("unsupported non-piping question")
        resolved = self.abspath(path)
        if not resolved.exists():
            return self.abstain(f"file not found: {resolved}")
        try:
            pages = _read_pdf(str(resolved))
        except (OSError, RuntimeError, ValueError) as exc:
            return self.abstain(f"could not read PDF: {exc}")
        page = _select_page(pages, question)
        if page is None:
            return self.abstain("named piping sheet was not found")

        if re.search(r"\b(?:HOW\s+LONG|LENGTH|SPACING|SPAN)\b", question, re.IGNORECASE):
            answer = _measurement_answer(path, page, question)
            return answer or self.abstain("could not measure the requested tagged span")

        if re.search(r"\b(?:CONNECT|COME\s+FROM|GO\s+TO|WHERE\s+DOES|WHAT\s+DOES)\b", question, re.IGNORECASE):
            answer = _connection_answer(path, resolved, page, question)
            return answer or self.abstain("could not resolve the requested connection")

        if "NOTE" in question.upper():
            answer = _note_answer(path, page, question)
            return answer or self.abstain("requested note was not found")

        if re.search(r"\b(?:SIZE|DIAMETER)\b", question, re.IGNORECASE):
            answer = _size_answer(path, page, question)
            return answer or self.abstain("named line size was not found")

        target = _count_target(question)
        if target is None or not re.search(r"\b(?:HOW\s+MANY|COUNT|NUMBER)\b", question, re.IGNORECASE):
            return self.abstain("unsupported piping question kind")

        family, distinct = target
        if family == "PS":
            matches = [("PS", word) for word in _bare_ps_words(page)]
        else:
            matches = [(tag, word) for tag, word in _word_tags(page) if tag == family or tag.startswith(family)]
        if distinct:
            unique: dict[str, _Word] = {}
            for tag, word in matches:
                unique.setdefault(tag, word)
            matches = list(unique.items())

        return Answer(
            value=len(matches),
            unit="count",
            confidence=0.98,
            evidence=[_evidence(path, page, tag, word) for tag, word in matches],
            trace=[
                f"selected PDF page {page.number}",
                f"parsed {family} tags from PyMuPDF word boxes",
                f"counted {'distinct IDs' if distinct else 'printed occurrences'}: {len(matches)}",
            ],
            solver=self.name,
            assumptions=["counted only explicit printed labels on the selected sheet"],
        )
