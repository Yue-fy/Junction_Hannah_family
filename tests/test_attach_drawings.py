"""experiments/r2/attach_drawings.py: Stoa's example questions as text -> eval rows (offline, no dataset reads)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "attach_drawings", Path(__file__).resolve().parents[1] / "experiments" / "r2" / "attach_drawings.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)


def test_parse_line_tags():
    assert ad.parse_line("# a comment") is None
    assert ad.parse_line("   ") is None
    r = ad.parse_line("[habs,finna][kind=state] In which state is it?")
    assert r == {"sources": ["habs", "finna"], "kind": "state", "question": "In which state is it?"}
    r = ad.parse_line("[data/swiss_dwellings/x.pdf][answer=3] How many bathrooms?")
    assert r["path"] == "data/swiss_dwellings/x.pdf" and r["answer"] == "3" and r["question"] == "How many bathrooms?"
    assert ad.parse_line("How big is room #3?")["question"] == "How big is room #3?"  # inline '#' is text


def test_attach_same_drawings_for_every_question(monkeypatch, tmp_path):
    pools = {"cubicasa5k": [f"data/cubicasa5k/{i}.png" for i in range(10)], "habs": [f"data/habs/{i}.jpg" for i in range(10)]}
    monkeypatch.setattr(ad, "_pool", lambda src, root: pools[src])
    rows = [{"question": "How many doors?"}, {"question": "What is this?", "sources": ["habs"], "answer": "12,5"},
            {"question": "Area?", "path": "data/swiss_dwellings/x.pdf", "kind": "area"}]
    out = ad.attach(rows, ("cubicasa5k", "habs"), 2, 0, tmp_path)
    q1 = [r for r in out if r["question"] == "How many doors?"]
    q2 = [r for r in out if r["question"] == "What is this?"]
    assert len(q1) == 4 and len(q2) == 2
    assert {r["path"] for r in q2} == {r["path"] for r in q1 if r["meta"]["source"] == "habs"}  # same sample
    assert q1[0]["type"] == "count" and q1[0]["answer"] is None and q1[0]["meta"]["kind"] == "q01"
    assert q2[0]["answer"] == 12.5
    given = [r for r in out if r["question"] == "Area?"]
    assert len(given) == 1 and given[0]["meta"] == {"kind": "area", "source": "swiss_dwellings", "from": "given"}
    assert ad.attach(rows, ("cubicasa5k", "habs"), 2, 0, tmp_path) == out  # deterministic
