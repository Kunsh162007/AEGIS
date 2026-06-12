"""The Command Center API: analyses file cases into the casebook, the officer
decides from the queue, KPIs and the intelligence briefing reflect it all.
Also covers the optional X-API-Key production auth."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.casework.department import reset_department

CSV = b"""from,to,amount,date,type
a1,MULE-7,9400,2026-03-01 10:00,TRANSFER
a2,MULE-7,9100,2026-03-01 11:00,TRANSFER
a3,MULE-7,9700,2026-03-01 12:30,TRANSFER
a4,MULE-7,8900,2026-03-01 14:00,TRANSFER
a5,MULE-7,9300,2026-03-01 15:00,TRANSFER
MULE-7,OFFSHORE-1,45900,2026-03-01 18:00,TRANSFER
EMPLOYER,bob,5200,2026-03-05 09:00,TRANSFER
"""


def _client() -> TestClient:
    reset_department()
    from src.api.main import app
    return TestClient(app)


def test_full_department_cycle_through_the_api():
    client = _client()

    # 1) An analysis files its verdicts in the casebook.
    r = client.post("/api/analyze?limit=1",
                    files={"file": ("ledger.csv", CSV, "text/csv")})
    assert r.status_code == 200
    filed = r.json()["results"][0]["case"]
    assert filed["status"] == "pending_review"
    assert filed["priority"] > 0

    # 2) It shows up in the review queue, highest priority first.
    queue = client.get("/api/cases?status=pending_review").json()["cases"]
    assert any(c["uid"] == filed["uid"] for c in queue)

    # 3) Case detail carries the full evidence chain and QA score.
    detail = client.get(f"/api/cases/{filed['uid']}").json()
    assert detail["result"]["evidence"]
    assert detail["qa_score"] is not None

    # 4) The officer decides; the policy threshold visibly moves.
    d = client.post(f"/api/cases/{filed['uid']}/decision",
                    json={"decision": "confirm"}).json()
    assert d["status"] == "confirmed_suspicious"
    again = client.post(f"/api/cases/{filed['uid']}/decision",
                        json={"decision": "confirm"})
    assert again.status_code == 409                    # no double decisions

    # 5) Operations KPIs reflect the closed case.
    ops = client.get("/api/operations").json()
    assert ops["confirmed_suspicious"] == 1
    assert ops["analyst_hours_saved"] > 0
    assert ops["recent_feedback"]

    # 6) The intelligence briefing reads the same casebook.
    brief = client.get("/api/intel/briefing").json()
    assert brief["cases_reviewed"] >= 1

    # 7) Unknown cases 404 cleanly.
    assert client.get("/api/cases/CASE-nope").status_code == 404
    assert client.post("/api/cases/CASE-nope/decision",
                       json={"decision": "dismiss"}).status_code == 404


def test_api_key_auth_when_configured(monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "api_key", "secret-key")
    client = _client()

    locked = client.post("/api/analyze?limit=1",
                         files={"file": ("l.csv", CSV, "text/csv")})
    assert locked.status_code == 401

    ok = client.post("/api/analyze?limit=1",
                     files={"file": ("l.csv", CSV, "text/csv")},
                     headers={"X-API-Key": "secret-key"})
    assert ok.status_code == 200

    # Read-only endpoints stay open for the dashboard.
    assert client.get("/api/operations").status_code == 200
