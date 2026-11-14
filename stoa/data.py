"""Dataset access: questions, paths, sibling formats, drawing groups, question templates.

Environment:
    STOA_DATA     full dataset root (contains questions.jsonl and data/)
    STOA_PREVIEW  preview dataset root (same layout)
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_DATA = "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"


def data_root() -> Path:
    return Path(os.environ.get("STOA_DATA", DEFAULT_DATA))


@dataclass(frozen=True)
class Question:
    qid: str  # stable id: sha1(path + question)[:12]
    path: str  # dataset-relative, "data/<source>/..."
    question: str
    answer: float | int | str | None
    unit: str | None
    type: str  # count | area | length | volume | text | other

    @property
    def source(self) -> str:
        return source_of(self.path)

    def to_dict(self) -> dict:
        return asdict(self)


def make_qid(path: str, question: str) -> str:
    return hashlib.sha1(f"{path}\n{question}".encode()).hexdigest()[:12]


def dataset_rel(path: str | Path, root: Path | None = None) -> str:
    """Any path to a dataset file -> the dataset-relative form ("data/<source>/...") that every cache, gate and split
    is keyed by. Relative paths are returned unchanged. An absolute path under the dataset root is made relative; one
    elsewhere (a copy of the dataset, another mount) is cut at its last "data/<source>/" component; any other absolute
    path (a drawing from outside the dataset) is returned unchanged."""
    p = Path(path)
    if not p.is_absolute():
        return str(path)
    try:
        return relpath(p, root)
    except ValueError:
        pass
    parts = p.parts
    for i in range(len(parts) - 3, -1, -1):  # need data/<source>/<file> at least
        if parts[i] == "data":
            return str(Path(*parts[i:]))
    return str(path)


def source_of(path: str) -> str:
    """Dataset source of a path ("cubicasa5k", "swiss_dwellings", ...); "unknown" for a file outside the dataset.
    Accepts relative ("data/cubicasa5k/x.png") and absolute paths (R1 03:44: absolute paths used to give "/")."""
    parts = Path(dataset_rel(path)).parts
    if not parts or Path(parts[0]).is_absolute():
        return "unknown"
    return parts[1] if len(parts) > 1 and parts[0] == "data" else parts[0]


def abspath(path: str, root: Path | None = None) -> Path:
    """Dataset-relative path -> absolute path on disk."""
    p = Path(path)
    return p if p.is_absolute() else (root or data_root()) / p


def relpath(path: str | Path, root: Path | None = None) -> str:
    """Absolute path -> dataset-relative string ("data/...")."""
    return str(Path(path).resolve().relative_to((root or data_root()).resolve()))


@functools.lru_cache(maxsize=4)
def load_questions(root: str | None = None) -> tuple[Question, ...]:
    """All questions from questions.jsonl (cached). Duplicated (path, question) pairs keep the first."""
    rootp = Path(root) if root else data_root()
    out, seen = [], set()
    with open(rootp / "questions.jsonl", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            qid = make_qid(r["path"], r["question"])
            if qid in seen:
                continue
            seen.add(qid)
            out.append(Question(qid, r["path"], r["question"], r.get("answer"), r.get("unit"), r.get("type", "other")))
    return tuple(out)


def siblings(path: str, root: Path | None = None) -> dict[str, str]:
    """Other formats of the same drawing: {".dxf": "data/.../x.dxf", ...} (same stem, same folder).

    For ifc_models PDFs/SVGs rendered from a model, the parent model is returned under key ".ifc".
    The asked file itself is included under its own extension.
    """
    rootp = root or data_root()
    p = Path(path)
    folder = abspath(str(p.parent), rootp)
    out: dict[str, str] = {}
    if folder.is_dir():
        for q in folder.iterdir():
            if q.stem == p.stem and q.is_file():
                out[q.suffix.lower()] = str(p.parent / q.name)
    if source_of(path) == "ifc_models" and ".ifc" not in out:
        model = ifc_model_for(path, rootp)
        if model:
            out[".ifc"] = model
    return out


@functools.lru_cache(maxsize=1)
def _ifc_models_stems(root: str) -> tuple[str, ...]:
    folder = Path(root) / "data" / "ifc_models"
    stems = [q.stem for q in folder.glob("*.ifc")] if folder.is_dir() else []
    return tuple(sorted(stems, key=len, reverse=True))  # longest first


def ifc_model_for(path: str, root: Path | None = None) -> str | None:
    """`data/ifc_models/<model>_<view>.pdf` -> `data/ifc_models/<model>.ifc` (longest matching model stem);
    `resbim-N_plan.png` -> `resbim-N_model.ifc`."""
    rootp = root or data_root()
    stem = Path(path).stem
    stems = _ifc_models_stems(str(rootp))
    for m in stems:
        if stem == m or stem.startswith(m + "_"):
            return f"data/ifc_models/{m}.ifc"
    # ResBIM pairs: resbim-N_plan.png (annotated raster plan) <-> resbim-N_model.ifc (W1, 00:31)
    base = re.sub(r"_plan$", "", stem)
    if base != stem and f"{base}_model" in stems:
        return f"data/ifc_models/{base}_model.ifc"
    return None


def drawing_group(path: str, root: Path | None = None) -> str:
    """Key used to split data: everything that shares information lands in the same split.

    - default: source + stem (all formats of one drawing)
    - ifc_models: the project of the parent IFC model (rendered plans share the model; discipline models
      and variants of one building share geometry)
    - ifc_bench: project = stem without the discipline suffix (dental_clinic_arc/_mep/_str -> dental_clinic)
    - swiss_dwellings: the site (floors of the same building are often identical)
    - opening_design: project folder + sheet
    """
    src = source_of(path)
    p = Path(path)
    if src == "ifc_models":
        # project = model stem before the first "_" (bsc-clinic_clinic-hvac -> bsc-clinic): discipline models
        # and near-duplicate variants of one building (vitoria_ald26-before/-project) stay together
        model = ifc_model_for(path, root)
        stem = Path(model).stem if model else p.stem
        return f"ifc_models/{stem.split('_', 1)[0]}"
    if src == "ifc_bench":
        return f"ifc_bench/{p.stem.rsplit('_', 1)[0] if '_' in p.stem else p.stem}"
    if src == "swiss_dwellings":
        m = re.match(r"(site\d+)", p.stem)
        return f"swiss_dwellings/{m.group(1) if m else p.stem}"
    if src == "opening_design":
        # per sheet: only 3 sheets carry questions, and they don't share facts (schedule vs enlarged plan)
        parts = p.parts
        return f"opening_design/{parts[2] if len(parts) > 3 else ''}/{p.stem}"
    return f"{src}/{p.stem}"


_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_QUOTED = re.compile(r"«[^»]{1,80}»|„[^“”\"]{1,80}[“”\"]|“[^”]{1,80}”|‘[^’]{1,80}’|(?<!\w)'[^']{1,80}'(?!\w)|\"[^\"]{1,80}\"")


def template_of(question: str) -> str:
    """Normalise a question to a template: quoted names -> <Q>, numbers -> <N>, lowercase, squashed spaces."""
    t = _QUOTED.sub("<Q>", question.lower())
    t = _NUM.sub("<N>", t)
    return re.sub(r"\s+", " ", t).strip()


_EN_START = re.compile(r"^\s*(how|what|which|is|are|does|do|on sheet|list|name|give)\b", re.I)


@functools.lru_cache(maxsize=4)
def concept_map(root: str | None = None) -> dict[str, str]:
    """qid -> concept id. The dataset asks many questions twice: in English and, on the next row, in the
    drawing's language (Finnish for cubicasa5k; German/French/Italian for swiss_dwellings), with the same
    answer. Both rows of such a pair share one concept id (the English question's qid); every other
    question is its own concept. Use it to avoid double-counting translations, or to test language
    robustness (same concept, other language)."""
    qs = load_questions(root)
    out: dict[str, str] = {}
    i = 0
    while i < len(qs):
        q = qs[i]
        if i + 1 < len(qs):
            n = qs[i + 1]
            if (n.path == q.path and n.type == q.type and n.answer == q.answer and n.unit == q.unit
                    and _EN_START.match(q.question) and not _EN_START.match(n.question)):
                out[q.qid] = out[n.qid] = q.qid
                i += 2
                continue
        out[q.qid] = q.qid
        i += 1
    return out
