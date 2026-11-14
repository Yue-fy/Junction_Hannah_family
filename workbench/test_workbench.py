"""Workbench checks (not in the repo-wide `tests/`; run: $JUNCTION_VENV/bin/python -m pytest -q workbench)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKBENCH_HUMAN_DIR", str(tmp_path / "human"))
    from workbench.app import app

    return TestClient(app)


BAD = ["../../etc/passwd", "data/../../../etc/passwd", "/etc/passwd", "data/cubicasa5k/LICENSE.md",
       "data/ifc_models/../../questions.jsonl", "questions.jsonl", "data/x\x00.png"]


@pytest.mark.parametrize("path", BAD)
def test_no_files_outside_drawings(client, path):
    for route in ("/api/img", "/api/view"):
        r = client.get(route, params={"path": path})
        assert r.status_code in (400, 404), (route, path, r.status_code)


def test_only_workbench_routes(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/static/app.py").status_code == 404
    assert client.get("/static/../app.py").status_code == 404


def test_rules_and_audit_roundtrip(client, tmp_path):
    r = client.post("/api/rules", json={"what": "door width", "min": "0,7", "max": "1.2", "unit": "m"})
    assert r.status_code == 200 and r.json()["saved"]["min"] == 0.7
    assert client.get("/api/rules").json()["rules"][0]["what"] == "door width"
    assert client.post("/api/audit", json={"item_id": "nope", "verdict": "supports"}).status_code == 404
    assert client.post("/api/audit", json={"item_id": "x", "verdict": "maybe"}).status_code == 422


def test_question_edit_and_delete(client):
    p = "data/swiss_dwellings/site990_bldg2071_floor9290.pdf"
    r = client.post("/api/questions", json={"path": p, "question": "How many rooms?", "answer": "7", "unit": "count",
                                            "type": "count"})
    assert r.status_code == 200, r.text
    qid = r.json()["saved"]["qid"]
    r = client.post("/api/questions", json={"path": p, "question": "How many rooms in apartment E?", "answer": "8",
                                            "unit": "count", "type": "count", "qid": qid})
    assert r.json()["saved"]["qid"] == qid and r.json()["n"] == 1
    qs = client.get("/api/questions").json()["questions"]
    assert len(qs) == 1 and qs[0]["answer"] == "8"
    assert client.post("/api/questions/delete", json={"qid": qid}).json()["n"] == 0
    assert client.get("/api/questions").json()["questions"] == []
