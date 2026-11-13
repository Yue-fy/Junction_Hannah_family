"""HTTP API for the demo (docs/CONTRACT.md). Run from the repo root:

    $JUNCTION_VENV/bin/python -m uvicorn stoa.api:app --port 8100

Endpoints: POST /ask, GET /file, GET /files, GET /questions, GET /intent, GET /health. CORS for the Vite dev
server on :5173. Answers are cached per (path, question, solver, kwargs) in memory.
"""

from __future__ import annotations

import collections
import functools
import json
import mimetypes
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from stoa.contract import Answer, CostMeter
from stoa.data import abspath, data_root, ifc_model_for, load_questions, siblings, source_of

app = FastAPI(title="Stoa blueprint QA (Team Hannah Family)", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for ext, typ in ((".ifc", "application/x-step"), (".dxf", "image/vnd.dxf"), (".svg", "image/svg+xml"),
                 (".jsonl", "application/jsonl")):
    mimetypes.add_type(typ, ext)


class AskRequest(BaseModel):
    path: str
    question: str
    solver: str = "pipeline"
    solver_args: dict = {}


_SOLVERS: dict[tuple, object] = {}
_SOLVER_LOCK = threading.Lock()
_ANSWERS: "collections.OrderedDict[tuple, dict]" = collections.OrderedDict()
_ANS_LOCK = threading.Lock()
_MAX_CACHE = 2000


def _solver(name: str, kwargs: dict):
    from stoa.solvers import get_solver

    key = (name, json.dumps(kwargs, sort_keys=True))
    with _SOLVER_LOCK:
        if key not in _SOLVERS:
            _SOLVERS[key] = get_solver(name, **kwargs)
        return _SOLVERS[key]


def _safe_rel(path: str) -> str:
    """Dataset-relative path under the data root, or 400/404."""
    if not path or ".." in Path(path).parts or path.startswith("/"):
        raise HTTPException(400, "path must be dataset-relative (data/...) without '..'")
    p = abspath(path).resolve()
    root = data_root().resolve()
    if root not in p.parents:
        raise HTTPException(400, "path outside the dataset")
    if not p.is_file():
        raise HTTPException(404, f"no such file: {path}")
    return path


@app.get("/health")
def health() -> dict:
    from stoa.solvers import available, import_errors

    return {"ok": True, "data_root": str(data_root()), "solvers": available(),
            "import_errors": sorted(import_errors())}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    path = _safe_rel(req.path)
    key = (path, req.question.strip(), req.solver, json.dumps(req.solver_args, sort_keys=True))
    with _ANS_LOCK:
        if key in _ANSWERS:
            _ANSWERS.move_to_end(key)
            return {**_ANSWERS[key], "cached": True}
    try:
        solver = _solver(req.solver, req.solver_args)
    except KeyError as e:
        raise HTTPException(400, str(e)) from e
    t0 = time.perf_counter()
    with CostMeter() as meter:
        ans = solver.solve(path, req.question)
    if not isinstance(ans, Answer):
        ans = Answer.model_validate(ans)
    rep, met = ans.cost.model_dump(), meter.cost.model_dump()
    ans.cost = ans.cost.model_validate({k: max(rep.get(k, 0) or 0, met.get(k, 0) or 0) for k in set(rep) | set(met)})
    if not ans.cost.wall_seconds:
        ans.cost.wall_seconds = round(time.perf_counter() - t0, 4)
    out = ans.model_dump()
    try:
        from stoa.router.intent import parse

        out["intent"] = parse(req.question).to_dict()
        from stoa.router.compose import decompose

        plan = decompose(source_of(path), req.question)
        if plan is not None:
            out["plan"] = {"op": plan.op, "parts": plan.labels, "sub_questions": plan.subs}
    except Exception:  # noqa: BLE001
        pass
    with _ANS_LOCK:
        _ANSWERS[key] = out
        while len(_ANSWERS) > _MAX_CACHE:
            _ANSWERS.popitem(last=False)
    return {**out, "cached": False}


@app.get("/file")
def get_file(path: str = Query(...)):
    path = _safe_rel(path)
    p = abspath(path)
    typ = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return FileResponse(p, media_type=typ, filename=p.name)


# --- file listing + licences -------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _questions_by_path() -> dict[str, list]:
    out = collections.defaultdict(list)
    for q in load_questions():
        out[q.path].append(q)
    return out


@functools.lru_cache(maxsize=16)
def _licences(source: str) -> tuple[tuple[str, str] | None, dict[str, tuple[str, str]]]:
    """(default (licence, credit), {file or stem: (licence, credit)}) parsed from data/<source>/LICENSE.md."""
    p = data_root() / "data" / source / "LICENSE.md"
    default, per = None, {}
    if not p.exists():
        return default, per
    text = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"All files:\s*(.+?)\.\s+Credit:\s*(.+)", text)
    if m:
        default = (m.group(1).strip(), m.group(2).strip())
    cols = None
    for line in text.splitlines():
        if not line.startswith("|"):
            cols = None if not line.strip() else cols
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if any(c in ("file", "model", "files") for c in low) and any("licen" in c for c in low):
            cols = {"file": next(i for i, c in enumerate(low) if c in ("file", "model", "files")),
                    "lic": next(i for i, c in enumerate(low) if "licen" in c),
                    "credit": next((i for i, c in enumerate(low) if "credit" in c or "copyright" in c), None)}
            continue
        if cols and not set(line) <= set("|-: ") and len(cells) > cols["lic"]:
            f = cells[cols["file"]].strip("`")
            cr = cells[cols["credit"]] if cols["credit"] is not None and len(cells) > cols["credit"] else ""
            per[f] = (cells[cols["lic"]], cr)
            per[Path(f).stem] = per[f]
    return default, per


def licence_of(path: str) -> tuple[str, str]:
    src = source_of(path)
    default, per = _licences(src)
    name = Path(path).name
    for k in (name, Path(path).stem):
        if k in per:
            return per[k]
    if src == "ifc_models":
        model = ifc_model_for(path)
        if model and Path(model).stem in per:
            return per[Path(model).stem]
    return default or ("see LICENSE.md", f"data/{src}/LICENSE.md")


@app.get("/files")
def files(source: str | None = None, q: str | None = None, limit: int = 50, with_questions: bool = True) -> dict:
    by_path = _questions_by_path()
    rows = []
    if with_questions:
        paths = sorted(by_path)
    else:
        base = data_root() / "data" / (source or "")
        paths = sorted(str(p.relative_to(data_root())) for p in base.rglob("*")
                       if p.is_file() and p.suffix.lower() not in (".md",))
    for p in paths:
        if source and source_of(p) != source:
            continue
        if q and q.lower() not in p.lower():
            continue
        lic, credit = licence_of(p)
        rows.append({"path": p, "source": source_of(p), "ext": Path(p).suffix.lower(), "siblings": siblings(p),
                     "n_questions": len(by_path.get(p, [])), "license": lic, "credit": credit})
        if len(rows) >= limit:
            break
    return {"files": rows}


@app.get("/questions")
def questions(path: str = Query(...), limit: int = 50) -> dict:
    qs = _questions_by_path().get(path, [])
    return {"questions": [{"question": q.question, "type": q.type, "unit": q.unit} for q in qs[:limit]]}


@app.get("/intent")
def intent(q: str = Query(...)) -> dict:
    from stoa.router.intent import parse

    return parse(q).to_dict()
