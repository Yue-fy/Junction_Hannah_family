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


def source_of(path: str) -> str:
    parts = Path(path).parts
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
    """`data/ifc_models/<model>_<view>.pdf` -> `data/ifc_models/<model>.ifc` (longest matching model stem)."""
    rootp = root or data_root()
    stem = Path(path).stem
    for m in _ifc_models_stems(str(rootp)):
        if stem == m or stem.startswith(m + "_"):
            return f"data/ifc_models/{m}.ifc"
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
_QUOTED = re.compile(r"(['\"‘’“”«»])(?:(?!\1).){1,80}\1")


def template_of(question: str) -> str:
    """Normalise a question to a template: quoted names -> <Q>, numbers -> <N>, lowercase, squashed spaces."""
    t = _QUOTED.sub("<Q>", question.lower())
    t = _NUM.sub("<N>", t)
    return re.sub(r"\s+", " ", t).strip()
