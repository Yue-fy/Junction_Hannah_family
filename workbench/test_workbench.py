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
