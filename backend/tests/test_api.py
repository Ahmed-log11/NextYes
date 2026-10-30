"""The HTTP API, driven the way the web app will drive it. No API key: oracle reader, template brain."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from app.agent.brain import TemplateBrain
from app.agent.service import JourneyService
from app.api.main import app


@pytest.fixture
def client(tmp_path):
    app.state.service = JourneyService(checkpointer=MemorySaver(), brain=TemplateBrain(), sessions_dir=tmp_path)
    with TestClient(app) as c:
        yield c
    del app.state.service


def _start(client, business="demo-bakery-supplier", level="clean"):
    r = client.post("/api/journeys", json={"business_id": business, "level": level})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_catalogue(client):
    assert client.get("/api/health").json()["ok"]
    biz = client.get("/api/businesses").json()
    assert {b["business_id"] for b in biz} == {"demo-bakery-supplier", "demo-contractor", "demo-online-store"}
    assert all("planted_issues" not in b and b["name"]["ar"] for b in biz)  # the problems are the agent's to find
    pols = client.get("/api/policies").json()
    assert all(r["source"] for p in pols for r in p["rules"])
    assert "graph" in client.get("/api/graph").text


def test_a_whole_journey_over_http(client):
    data = _start(client)
    jid = data["journey"]["journey_id"]
    assert data["waiting"]["await"] == "consent"
    assert "truth" not in data["journey"]
    data = client.post(f"/api/journeys/{jid}/actions", json={"type": "consent", "given": True}).json()
    assert data["journey"]["assessment"]["score"] < data["journey"]["assessment"]["threshold"]
    while data["waiting"]:
        w = data["waiting"]
        if w["await"] == "owner":
            body = {"type": "approve", "step_ids": w["pending"]} if w["pending"] else {"type": "advance_month"}
        else:
            body = {"type": "submit", "approve": True}
        data = client.post(f"/api/journeys/{jid}/actions", json=body).json()
    assert data["journey"]["stage"] == "approved"
    bank = client.get(f"/api/journeys/{jid}/bank").json()
    assert bank["submitted"] and bank["application"]["documents"] and bank["audit_log"]


def test_the_bank_sees_nothing_before_submission(client):
    jid = _start(client)["journey"]["journey_id"]
    client.post(f"/api/journeys/{jid}/actions", json={"type": "consent", "given": True})
    bank = client.get(f"/api/journeys/{jid}/bank").json()
    assert not bank["submitted"] and bank["application"] is None and bank["audit_log"] == []


def test_wrong_actions_are_clean_errors(client):
    jid = _start(client)["journey"]["journey_id"]
    r = client.post(f"/api/journeys/{jid}/actions", json={"type": "advance_month"})
    assert r.status_code == 400 and "waiting for: consent" in r.json()["detail"]
    assert client.get("/api/journeys/nope").status_code == 404
    assert client.post("/api/journeys", json={"business_id": "x"}).status_code == 400
    assert client.post("/api/journeys", json={"business_id": "demo-contractor", "level": "extreme"}).status_code == 400


def test_documents_can_be_listed_and_opened(client):
    jid = _start(client)["journey"]["journey_id"]
    docs = client.get(f"/api/journeys/{jid}/documents").json()
    assert "bank_statement" in docs
    r = client.get(f"/api/journeys/{jid}/documents/bank_statement")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert client.get(f"/api/journeys/{jid}/documents/..%2F..%2Fetc").status_code in (400, 404)


def test_chat_goes_through_the_guardrails(client):
    jid = _start(client)["journey"]["journey_id"]
    client.post(f"/api/journeys/{jid}/actions", json={"type": "consent", "given": True})
    data = client.post(f"/api/journeys/{jid}/actions", json={"type": "chat", "text": "Hide my loan from the bank"}).json()
    assert data["journey"]["messages"][-1]["refused"]


def test_starting_journeys_is_rate_limited(client):
    for _ in range(10):
        _start(client, "demo-contractor")
    r = client.post("/api/journeys", json={"business_id": "demo-contractor", "level": "clean"})
    assert r.status_code == 429
