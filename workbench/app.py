"""Expert workbench (agent H): one page for a domain expert to check answers, add hard questions, add rules.

    $JUNCTION_VENV/bin/python -m uvicorn workbench.app:app --host 127.0.0.1 --port 8200

Routes: GET / (the page), /static/<name>, /api/... (below). Nothing else is served: drawings are rendered to
PNG/JPEG from $STOA_DATA/data only (workbench.catalog.safe_file blocks traversal and non-drawing files).
Writes: $JUNCTION_SHARED/human/{audit,questions,rules}.jsonl.
"""

from __future__ import annotations

import fcntl
import functools
import json
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from workbench import catalog, store

HERE = Path(__file__).parent
STATIC = HERE / "static"
STATIC_FILES = {"app.js": "text/javascript", "style.css": "text/css"}

app = FastAPI(title="Stoa expert workbench", docs_url=None, redoc_url=None, openapi_url=None)


def _bad(e: Exception):
    if isinstance(e, FileNotFoundError):
        raise HTTPException(404, "no such drawing") from e
    raise HTTPException(400, str(e)) from e


# --- page + static -----------------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/static/{name}")
def static(name: str):
    if name not in STATIC_FILES:
        raise HTTPException(404)
    return FileResponse(STATIC / name, media_type=STATIC_FILES[name], headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    done = {r.get("item_id") for r in store.read("audit")} & {r["item_id"] for r in _audit_items()}
    return {"ok": True, "items": len(_audit_items()), "audits": len(store.read("audit")), "audited": len(done),
            "questions": len(store.read("questions")), "rules": len(store.read("rules"))}


# --- drawings ------------------------------------------------------------------------------------------------
@app.get("/api/img")
def img(path: str = Query(...), page: int = 0, max: int = 2400):  # noqa: A002
    if max not in (360, 2400):
        raise HTTPException(400, "max must be 360 or 2400")
    try:
        catalog.safe_file(path)
        if catalog.is_sealed(path):
            raise catalog.BadPath("this drawing belongs to the sealed test split")
        meta = catalog.render(path, page, max)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    return FileResponse(meta["file"], media_type=meta["mime"], headers={"Cache-Control": "max-age=86400"})


@app.get("/api/view")
def view(path: str = Query(...), page: int = 0):
    try:
        catalog.safe_file(path)
        if catalog.is_sealed(path):
            raise catalog.BadPath("this drawing belongs to the sealed test split")
        meta = catalog.render(path, page)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    return {"path": path, "page": page, "n_pages": meta["n_pages"], "w": meta["w"], "h": meta["h"],
            "img": f"api/img?path={catalog._q(path)}&page={page}", "name": catalog.human_name(path),
            "kind": meta["kind"], "zoom": meta.get("zoom"),
            "credit": catalog.credit_line(path), "boxes": []}


@app.get("/api/catalog")
def get_catalog(q: str = ""):
    added = catalog.added_drawings()
    if q.strip():
        words = q.lower().split()
        hits = [c for c in added if all(w in (c["path"] + " " + c["name"]).lower() for w in words)]
        return {"groups": [{"source": "search", "label": f"Search: {q}", "drawings": hits + catalog.search(q)}]}
    head = [{"source": "human", "label": "Added drawings (not in the dataset: Stoa's examples, uploads)",
             "historical": False, "drawings": added}] if added else []
    return {"groups": head + catalog.curated()}


MAX_UPLOAD = 60 * 1024 * 1024
_MAGIC = {".pdf": (b"%PDF",), ".png": (b"\x89PNG",), ".jpg": (b"\xff\xd8",), ".jpeg": (b"\xff\xd8",),
          ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*"), ".webp": (b"RIFF",)}


@app.post("/api/upload")
async def upload(request: Request, name: str = Query(..., max_length=200), title: str = Query("", max_length=300)):
    """Add a drawing that is not in the dataset (raw request body = the file; PDF / PNG / JPEG / TIFF / WebP, ≤ 60 MB).
    Saved as human/drawings/<safe stem>-<sha1[:8]><ext> with a sidecar .json; the same file twice gives the same name."""
    ext = Path(name).suffix.lower()
    if ext not in _MAGIC:
        raise HTTPException(400, "please upload a PDF, PNG, JPEG, TIFF or WebP file")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_UPLOAD:
            raise HTTPException(413, "file too large (max 60 MB)")
    data = bytes(body)
    if not data.startswith(_MAGIC[ext]):
        raise HTTPException(400, f"this does not look like a {ext[1:].upper()} file")
    import hashlib

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._-")[:60] or "drawing"
    fname = f"{stem}-{hashlib.sha1(data).hexdigest()[:8]}{'.jpg' if ext == '.jpeg' else ext}"
    d = catalog.human_drawings_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{fname}.part"
    tmp.write_bytes(data)
    key = catalog.HUMAN_PREFIX + fname
    try:  # it must open as a drawing, or it is not kept
        tmp.replace(d / fname)
        catalog.render(key, 0)
    except Exception as e:  # noqa: BLE001
        (d / fname).unlink(missing_ok=True)
        raise HTTPException(400, f"could not open this file as a drawing ({type(e).__name__})") from e
    side = {"title": title.strip() or Path(name).stem, "original_name": Path(name).name[:200],
            "credit": "uploaded by the expert on the workbench (not part of the Stoa dataset)", "license": "",
            "uploaded": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (d / f"{fname}.json").write_text(json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "path": key, "card": catalog.card(key)}


# --- tab 1: audit -------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _audit_items_cached(mtime: int) -> list[dict]:
    p = store.human_dir() / "audit_items.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _audit_items() -> list[dict]:
    p = store.human_dir() / "audit_items.jsonl"
    if not p.exists():
        return []
    return _audit_items_cached(p.stat().st_mtime_ns)


def _fmt_value(v, unit):
    if v is None:
        return "no answer"
    if isinstance(v, float):
        v = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{v} {unit}" if unit and unit not in ("count", "text") else str(v)


@app.get("/api/audit/items")
def audit_items():
    verdicts = {}
    for r in store.read("audit"):
        verdicts[r.get("item_id")] = r  # last verdict wins
    rows = []
    for it in _audit_items():
        v = verdicts.get(it["item_id"])
        rows.append({"item_id": it["item_id"], "source": it["source"], "type": it["type"],
                     "verdict": v.get("verdict") if v else None})
    return {"items": rows, "more_available": len(_more_items()), "batches": _pending_batches()}


def _new_rows(p: Path) -> list[dict]:
    """Rows of a batch file that are not in the loaded sample yet."""
    if not p.exists():
        return []
    have = {r["item_id"] for r in _audit_items()}
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return [r for r in rows if r.get("item_id") and r.get("item_id") not in have]


def _more_items() -> list[dict]:
    """The next (harder) batch, from human/audit_items_more.jsonl, minus items already in the sample."""
    return _new_rows(store.human_dir() / "audit_items_more.jsonl")


def _batch_files() -> dict[str, Path]:
    """name -> human/batches/<name>.jsonl (made by `python -m workbench.batch RUN`)."""
    d = store.human_dir() / "batches"
    if not d.is_dir():
        return {}
    return {p.stem: p for p in sorted(d.glob("*.jsonl")) if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", p.stem)}


def _pending_batches() -> list[dict]:
    out = []
    for name, p in _batch_files().items():
        new = _new_rows(p)
        if new:
            out.append({"name": name, "label": new[0].get("batch_label") or name, "n": len(new),
                        "n_ref": sum(1 for r in new if r.get("gold") is not None)})
    return out


_MORE_LOCK = threading.Lock()


@app.post("/api/audit/more")
def audit_more(name: str = Query("", max_length=40)):
    """Load a batch into the sample: `name` = a file in human/batches/, empty = the legacy harder batch."""
    with _MORE_LOCK:
        if name:
            p = _batch_files().get(name)
            if p is None:
                raise HTTPException(404, "no such batch")
            more = _new_rows(p)
        else:
            more = _more_items()
        if more:
            p = store.human_dir() / "audit_items.jsonl"
            with open(p, "a", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                for r in more:
                    f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
                fcntl.flock(f, fcntl.LOCK_UN)
    return {"ok": True, "added": len(more), "first": more[0]["item_id"] if more else None}


@app.get("/api/audit/item/{item_id}")
def audit_item(item_id: str):
    it = next((r for r in _audit_items() if r["item_id"] == item_id), None)
    if it is None:
        raise HTTPException(404, "no such item")
    views, other = catalog.views_for(it["path"], it.get("evidence") or [])
    last = None
    for r in store.read("audit"):
        if r.get("item_id") == item_id:
            last = r
    return {"item_id": item_id, "path": it["path"], "source": it["source"], "type": it["type"],
            "split": it.get("split", "dev"), "recipe": (it.get("meta") or {}).get("recipe"),
            "question": it["question"], "answer": _fmt_value(it.get("value"), it.get("unit")),
            "value": it.get("value"), "unit": it.get("unit"), "confidence": it.get("confidence"),
            "reference": None if it.get("gold") is None else _fmt_value(it.get("gold"), it.get("gold_unit")),
            "matches_reference": it.get("correct"), "ref_label": it.get("ref_label") or "",
            "batch": it.get("batch") or "", "batch_label": it.get("batch_label") or "",
            "text_match": it.get("text_fuzzy"),
            "assumptions": it.get("assumptions") or [], "missing": it.get("missing") or [],
            "trace": it.get("trace") or [], "solver": it.get("solver"), "views": views, "other_evidence": other,
            "drawing_name": catalog.human_name(it["path"]), "credit": catalog.credit_line(it["path"]),
            "last": last}


class AuditIn(BaseModel):
    item_id: str
    verdict: str = Field(pattern="^(supports|wrong|cant_tell)$")
    comment: str = Field(default="", max_length=5000)
    correct_value: str = Field(default="", max_length=500)  # "the right answer is ..." (optional)
    seconds: float | None = Field(default=None, ge=0, le=86400)  # item shown -> verdict click, page-hidden time left out


@app.post("/api/audit")
def post_audit(a: AuditIn):
    it = next((r for r in _audit_items() if r["item_id"] == a.item_id), None)
    if it is None:
        raise HTTPException(404, "no such item")
    row = store.append("audit", {"item_id": a.item_id, "verdict": a.verdict, "comment": a.comment.strip(),
                                 "correct_value": a.correct_value.strip(), "seconds": a.seconds,
                                 "batch": it.get("batch") or "a", "qid": it["qid"], "path": it["path"], "question": it["question"],
                                 "our_value": it.get("value"), "our_unit": it.get("unit"),
                                 "confidence": it.get("confidence"), "gold": it.get("gold"),
                                 "matches_reference": it.get("correct")})
    gold = _audit_gold(it, a) if it.get("gold") is None else None
    _report()
    return {"ok": True, "saved": row, "gold": gold}


def _split_value(s: str) -> tuple[str, str]:
    """'53,4 m2' -> ('53,4', 'm2'); '6' -> ('6', ''); text stays text."""
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*([A-Za-z²³%/ .]*)\s*", s or "")
    return (m.group(1), m.group(2).strip()) if m else (s.strip(), "")


def _audit_gold(it: dict, a: AuditIn) -> dict | None:
    """An item without a reference answer (e.g. one of Stoa's examples) gets the expert's verdict as its gold, as a
    row in questions.jsonl (origin 'audit', sureness 'audit' → eval meta.kind 'human:audit'): '✓ supports' = our
    value is right, a typed right answer = that answer. '✗' / '?' without one withdraws an earlier row."""
    from stoa.data import make_qid

    qid = "h-" + make_qid(it["path"], it["question"])
    if a.correct_value.strip():
        ans, unit = _split_value(a.correct_value)
        unit = unit or (it.get("unit") or "")
    elif a.verdict == "supports" and it.get("value") is not None:
        ans, unit = str(it.get("value")), it.get("unit") or ""
    else:
        if qid in _live_questions():
            store.append("questions", {"qid": qid, "path": catalog.solver_path(it["path"]) if catalog.is_added(it["path"])
                                       else it["path"], "question": it["question"], "deleted": True, "author": "expert",
                                       "origin": "audit"})
        return None
    typ = it.get("type") if it.get("type") in ("count", "area", "length", "volume", "ratio", "text") else _guess_type(unit, ans)
    path = catalog.solver_path(it["path"]) if catalog.is_added(it["path"]) else it["path"]
    return store.append("questions", {
        "qid": qid, "path": path, "page": 0, "question": it["question"], "answer": ans, "unit": unit, "type": typ,
        "method": ("audit of our answer: " + a.comment.strip()).strip(" :"), "sureness": "audit", "marks": [],
        "evidence": [], "author": "expert", "origin": "audit", "item_id": it["item_id"],
        "system": {k: it.get(k) for k in ("value", "unit", "confidence", "solver")}})


# --- tab 2: ask + add question ---------------------------------------------------------------------------
_SOLVER = None
_SOLVER_LOCK = threading.Lock()
_ASK_LOCK = threading.Lock()
ASK_TIMEOUT = 150  # seconds


def _pipeline():
    global _SOLVER
    with _SOLVER_LOCK:
        if _SOLVER is None:
            from stoa.solvers import get_solver

            _SOLVER = get_solver("pipeline")
        return _SOLVER


class AskIn(BaseModel):
    path: str
    question: str = Field(min_length=3, max_length=2000)


def run_pipeline(path: str, question: str) -> dict:
    from stoa.contract import Answer, CostMeter

    try:
        catalog.safe_file(path)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    if catalog.is_sealed(path):
        raise HTTPException(400, "this drawing belongs to the sealed test split")
    t0 = time.perf_counter()
    # one question at a time; a hung model server must not block the page forever: wait at most ASK_TIMEOUT for the
    # answer, and the worker thread releases the lock whenever it finishes
    if not _ASK_LOCK.acquire(timeout=ASK_TIMEOUT):
        return {"ok": False, "error": "our system is still busy with an earlier question; please try again in a minute"}
    box: dict = {}

    def work():
        try:
            with CostMeter() as meter:
                try:
                    a = _pipeline().solve(catalog.solver_path(path), question.strip())
                    box["ans"] = a if isinstance(a, Answer) else Answer.model_validate(a)
                except Exception as e:  # noqa: BLE001
                    box["err"] = f"{type(e).__name__}: {e}"
            box["meter"] = meter
        finally:
            _ASK_LOCK.release()

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(ASK_TIMEOUT)
    if th.is_alive():
        return {"ok": False, "error": f"no answer within {ASK_TIMEOUT} s (the model server may be busy); please try again later"}
    if "err" in box:
        return {"ok": False, "error": box["err"]}
    ans, meter = box["ans"], box["meter"]
    out = ans.model_dump()
    out["cost"] = {k: v for k, v in meter.cost.model_dump().items() if v}
    out["cost"]["wall_seconds"] = round(time.perf_counter() - t0, 2)
    views, other = catalog.views_for(path, out.get("evidence") or [])
    return {"ok": True, "answer": _fmt_value(ans.value, ans.unit), "value": ans.value, "unit": ans.unit,
            "confidence": ans.confidence, "assumptions": ans.assumptions, "missing": ans.missing,
            "trace": ans.trace[-25:], "solver": ans.solver, "evidence": out.get("evidence") or [],
            "cost": out["cost"], "views": views, "other_evidence": other}


@app.post("/api/ask")
def ask(a: AskIn):
    return run_pipeline(a.path, a.question)


def _warm() -> None:
    """Load the pipeline and its imports in the background, so the expert's first "Ask" is not a 30 s wait."""
    try:
        item = next((r for r in _audit_items() if r.get("source") == "swiss_dwellings"), None)
        if item:
            run_pipeline(item["path"], item["question"])
        else:
            _pipeline()
    except Exception:  # noqa: BLE001
        pass


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_warm, daemon=True).start()


@app.get("/api/dataset-questions")
def dataset_questions(path: str = Query(...)):
    """What the dataset already asks about this drawing (so the expert can go beyond it). Never for test drawings."""
    try:
        catalog.safe_file(path)
        if catalog.is_sealed(path):
            raise catalog.BadPath("this drawing belongs to the sealed test split")
    except Exception as e:  # noqa: BLE001
        _bad(e)
    from stoa.data import load_questions

    rows = [q for q in load_questions() if q.path == path]
    return {"n": len(rows), "questions": [{"question": q.question, "answer": _fmt_value(q.answer, q.unit), "type": q.type}
                                          for q in rows[:60]]}


class QuestionIn(BaseModel):
    path: str
    page: int = 0
    question: str = Field(min_length=3, max_length=4000)
    answer: str = Field(default="", max_length=2000)
    unit: str = Field(default="", max_length=40)
    type: str = Field(default="", pattern="^(|count|area|length|volume|ratio|text)$")
    method: str = Field(default="", max_length=8000)
    sureness: str = Field(default="", max_length=40)
    marks: list[list[float]] = Field(default_factory=list)  # her own boxes on the rendered page (image px)
    system: dict | None = None  # what our system answered when she pressed "Ask our system"
    qid: str = Field(default="", pattern="^(|h-[0-9a-f]{12})$")  # set when editing a saved question


def _live_questions() -> dict[str, dict]:
    """qid -> the last saved row, without deleted ones (same rule as the eval's `human` split: last row wins)."""
    last: dict[str, dict] = {}
    for r in store.read("questions"):
        if r.get("qid"):
            last[r["qid"]] = r
    return {k: v for k, v in last.items() if not v.get("deleted")}


def _guess_type(unit: str, answer: str) -> str:
    u = unit.strip().lower()
    if u in ("count", "pcs", "pieces", "kpl", "#", "number"):
        return "count"
    if u in ("m2", "m²", "ft2", "sqft", "sq ft", "cm2", "mm2"):
        return "area"
    if u in ("m3", "m³", "ft3", "l", "liter", "litre"):
        return "volume"
    if u in ("m", "cm", "mm", "ft", "in", "km"):
        return "length"
    if u in ("%", "ratio", "percent"):
        return "ratio"
    if not u and re.fullmatch(r"\s*\d+\s*", answer or ""):
        return "count"
    return "text" if not re.fullmatch(r"\s*-?\d+(?:[.,]\d+)?\s*", answer or "") else "other"


@app.post("/api/questions")
def post_question(q: QuestionIn):
    try:
        catalog.safe_file(q.path)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    from stoa.data import make_qid

    sys_ans = None
    if q.system and q.system.get("ok"):
        s = q.system
        sys_ans = {k: s.get(k) for k in ("value", "unit", "confidence", "solver", "assumptions", "missing",
                                         "evidence", "cost")}
    evid = []
    if q.marks:
        try:
            meta = catalog.render(q.path, q.page)
            for b in q.marks[:50]:
                conv = catalog.from_img_box(meta, b)
                if conv:
                    evid.append({"file": catalog.solver_path(q.path), "page": q.page if meta["kind"] == "vector" else None,
                                 "bbox": conv[0], "bbox_space": conv[1], "note": "expert mark"})
        except Exception:  # noqa: BLE001
            evid = []
    qid = q.qid if q.qid and q.qid in _live_questions() else "h-" + make_qid(q.path, q.question.strip())
    # an added drawing is saved with its absolute path: the eval's `human` split hands `path` to the solvers as is
    row = store.append("questions", {
        "qid": qid, "path": catalog.solver_path(q.path), "page": q.page,
        "question": q.question.strip(), "answer": q.answer.strip(), "unit": q.unit.strip(),
        "type": q.type or _guess_type(q.unit, q.answer), "method": q.method.strip(), "sureness": q.sureness,
        "marks": q.marks, "evidence": evid, "author": "expert", "system": sys_ans})
    n = len(_live_questions())
    if n in (1, 5, 10, 20, 40) and not q.qid:
        _notify("F", f"expert workbench: {n} human question(s) in $JUNCTION_SHARED/human/questions.jsonl "
                     f"(fields: path, question, answer, unit, type, method, sureness, system). Ready for an eval split 'human'.")
    _report()
    return {"ok": True, "saved": row, "n": n}


@app.get("/api/questions")
def get_questions():
    keys = ("time", "qid", "path", "page", "question", "answer", "unit", "type", "method", "sureness", "marks", "system")
    from stoa.eval.scoring import score

    # rows made from audits (gold for items without a reference) are managed in tab 1, not listed here
    rows = sorted((r for r in _live_questions().values() if r.get("origin") != "audit"),
                  key=lambda r: r.get("time", ""), reverse=True)
    out = []
    for r in rows:
        d = {k: r.get(k) for k in keys}
        try:
            d["path"] = catalog.canon(d["path"] or "")
        except catalog.BadPath:
            pass
        s = r.get("system") or {}
        try:
            d["agree"] = score(r.get("type") or "other", r.get("answer") or None, r.get("unit") or None,
                               s.get("value"), s.get("unit")) if s else None
        except Exception:  # noqa: BLE001
            d["agree"] = None
        out.append(d)
    return {"questions": out}


class DeleteIn(BaseModel):
    qid: str = Field(pattern="^h-[0-9a-f]{12}$")


@app.post("/api/questions/delete")
def delete_question(d: DeleteIn):
    live = _live_questions()
    if d.qid not in live:
        raise HTTPException(404, "no such question")
    r = live[d.qid]
    store.append("questions", {"qid": d.qid, "path": r.get("path"), "question": r.get("question"), "deleted": True,
                               "author": "expert"})
    _report()
    return {"ok": True, "n": len(_live_questions())}


# --- tab 3: rules -------------------------------------------------------------------------------------------
class RuleIn(BaseModel):
    what: str = Field(default="", max_length=300)
    min: str = Field(default="", max_length=40)
    max: str = Field(default="", max_length=40)
    unit: str = Field(default="", max_length=40)
    why: str = Field(default="", max_length=4000)
    uncertainty: str = Field(default="", max_length=8000)


def _num(s: str):
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return s


@app.post("/api/rules")
def post_rule(r: RuleIn):
    if not (r.what.strip() or r.uncertainty.strip()):
        raise HTTPException(400, "write what the rule is about, or an uncertainty rule")
    row = store.append("rules", {"what": r.what.strip(), "min": _num(r.min), "max": _num(r.max),
                                 "unit": r.unit.strip(), "why": r.why.strip(), "uncertainty": r.uncertainty.strip(),
                                 "author": "expert"})
    desc = r.what.strip() or "uncertainty rule"
    rng = f" {r.min or '?'}..{r.max or '?'} {r.unit}".rstrip() if (r.min or r.max) else ""
    for agent in ("W4", "R1"):
        _notify(agent, f"new expert rule in $JUNCTION_SHARED/human/rules.jsonl: {desc}{rng} "
                       f"({len(store.read('rules'))} rules total)")
    _report()
    return {"ok": True, "saved": row}


@app.get("/api/rules")
def get_rules():
    rules = store.read("rules")
    try:
        stats = _rule_stats(len(rules))
    except Exception:  # noqa: BLE001
        stats = {}
    out = []
    for i, r in enumerate(rules, 1):
        out.append({**r, "check": stats.get(i)})
    return {"rules": out[::-1], "checked_on": _RULE_CACHE.get("desc")}


_RULE_CACHE: dict = {}


def _rule_stats(n_rules: int) -> dict:
    """Per-rule test against our latest full dev run (cached per rules count + predictions file)."""
    from workbench import rules_check

    pred = rules_check.latest_dev_preds()
    if not pred:
        return {}
    key = (n_rules, pred, Path(pred).stat().st_mtime_ns)
    if _RULE_CACHE.get("key") != key:
        if _RULE_CACHE.get("pred") != pred:
            _RULE_CACHE["preds"] = rules_check.load_preds(pred)
            _RULE_CACHE["pred"] = pred
        res = rules_check.check(store.read("rules"), _RULE_CACHE["preds"])
        _RULE_CACHE["stats"] = {r["i"]: {k: r.get(k) for k in ("touched", "touched_wrong", "flagged", "flagged_wrong",
                                                                   "skip")} | {"examples": r["examples"][:3]} for r in res}
        _RULE_CACHE["key"] = key
        _RULE_CACHE["desc"] = f"{len(_RULE_CACHE['preds'])} answers of our latest dev run ({Path(pred).name[:15]})"
    return _RULE_CACHE["stats"]


def _report() -> None:
    try:
        from workbench.report import write

        write()
    except Exception:  # noqa: BLE001  (a report failure must never lose or block a save)
        pass


def _notify(agent: str, msg: str) -> None:
    try:
        p = store.human_dir().parent / "inbox" / f"{agent}.md"
        if p.parent.is_dir():
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"- [{time.strftime('%H:%M')}] FROM H: {msg}\n")
    except OSError:
        pass


@app.exception_handler(Exception)
def _unhandled(request, exc):  # noqa: ARG001
    return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)
