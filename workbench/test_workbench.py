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


BAD_ADDED = ["human/drawings/../audit.jsonl", "human/drawings/../../human/rules.jsonl", "human/drawings/sub/x.png",
             "human/drawings/", "human/drawings/.hidden.png", "human/drawings/x.png.json", "human/x.png"]


def _png(path, w=40, h=30):
    from PIL import Image

    Image.new("RGB", (w, h), "white").save(path)


@pytest.mark.parametrize("path", BAD_ADDED)
def test_added_folder_blocks_traversal(client, tmp_path, path):
    d = tmp_path / "human" / "drawings"
    d.mkdir(parents=True)
    _png(d / "ok.png")
    (tmp_path / "human" / "audit.jsonl").write_text("{}\n")
    assert client.get("/api/img", params={"path": "human/drawings/ok.png"}).status_code == 200
    for route in ("/api/img", "/api/view"):
        r = client.get(route, params={"path": path})
        assert r.status_code in (400, 404), (route, path, r.status_code)


def test_upload_checks_and_lists(client, tmp_path):
    src = tmp_path / "plan.png"
    _png(src)
    assert client.post("/api/upload", params={"name": "x.exe"}, content=b"MZ").status_code == 400
    assert client.post("/api/upload", params={"name": "fake.pdf"}, content=b"<html>").status_code == 400
    r = client.post("/api/upload", params={"name": "my plan.png"}, content=src.read_bytes())
    assert r.status_code == 200, r.text
    key = r.json()["path"]
    assert key.startswith("human/drawings/my_plan-") and key.endswith(".png")
    groups = client.get("/api/catalog").json()["groups"]
    assert groups[0]["source"] == "human" and groups[0]["drawings"][0]["path"] == key
    # a question on it is saved with the absolute path (the eval's `human` split opens it as is) and read back as key
    r = client.post("/api/questions", json={"path": key, "question": "How many rooms?", "answer": "3", "unit": "count"})
    assert r.status_code == 200 and r.json()["saved"]["path"].startswith(str(tmp_path))
    assert client.get("/api/questions").json()["questions"][0]["path"] == key


def test_batch_from_run_without_reference(client, tmp_path, monkeypatch):
    import json

    from workbench import batch

    outside = tmp_path / "stoa_examples"
    outside.mkdir()
    _png(outside / "example sheet.png")
    rows = [{"qid": "q1", "path": str(outside / "example sheet.png"), "question": "How many doors?", "type": "count",
             "source": "unknown", "gold": None, "value": 4, "unit": "count", "confidence": 0.4, "correct": None,
             "evidence": [{"file": str(outside / "example sheet.png"), "bbox": [1, 1, 5, 5], "note": "door"}]},
            {"qid": "q2", "path": "data/swiss_dwellings/site990_bldg2071_floor9290.pdf", "question": "Area?",
             "type": "area", "source": "swiss_dwellings", "gold": 50.0, "gold_unit": "m2", "value": 50.2, "unit": "m2",
             "confidence": 0.9, "correct": True, "evidence": []}]
    pf = tmp_path / "run.jsonl"
    pf.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert batch.main([str(pf), "--name", "stoa", "--label", "Stoa examples", "--ref-label", "Stoa"]) == 0
    b = client.get("/api/audit/items").json()["batches"]
    assert b == [{"name": "stoa", "label": "Stoa examples", "n": 2, "n_ref": 1}]
    assert client.post("/api/audit/more", params={"name": "../x"}).status_code == 404
    r = client.post("/api/audit/more", params={"name": "stoa"}).json()
    assert r["added"] == 2
    items = client.get("/api/audit/items").json()
    assert items["batches"] == [] and len(items["items"]) == 2
    it = client.get(f"/api/audit/item/{r['first']}").json()
    q1 = it if it["path"].startswith("human/") else client.get(f"/api/audit/item/{items['items'][1]['item_id']}").json()
    assert q1["path"].startswith("human/drawings/example_sheet-") and q1["reference"] is None
    assert q1["views"] and q1["views"][0]["boxes"], "the evidence box must land on the copied drawing"
    r = client.post("/api/audit", json={"item_id": q1["item_id"], "verdict": "wrong", "correct_value": "3", "seconds": 12.5})
    assert r.json()["saved"]["seconds"] == 12.5 and r.json()["saved"]["batch"] == "stoa"
    # no reference → her answer becomes a gold row of the eval's `human` split, with a path the solvers can open
    from stoa.eval.splits import _human_rows

    hr = _human_rows(tmp_path / "human" / "questions.jsonl")
    assert len(hr) == 1 and hr[0]["answer"] == 3 and hr[0]["type"] == "count" and hr[0]["meta"]["kind"] == "human:audit"
    assert hr[0]["path"].startswith(str(tmp_path)) and client.get("/api/questions").json()["questions"] == []
    # '?' afterwards withdraws it; '✓' on our answer makes our value the gold
    client.post("/api/audit", json={"item_id": q1["item_id"], "verdict": "cant_tell"})
    last = json.loads((tmp_path / "human" / "questions.jsonl").read_text().splitlines()[-1])
    assert last["deleted"] is True and last["qid"] == hr[0]["qid"]
    assert _human_rows(tmp_path / "human" / "questions.jsonl") == []  # the eval drops it (night-F ff1e88e)
    client.post("/api/audit", json={"item_id": q1["item_id"], "verdict": "supports"})
    assert _human_rows(tmp_path / "human" / "questions.jsonl")[0]["answer"] == 4
