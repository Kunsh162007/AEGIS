"""The new product surface: Ask-AEGIS chat, the typology library, org
profile/history endpoints, dataset heat-marking, and the benchmark removal."""
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

HISTORY = b"""from,to,amount,date,type
EMPLOYER,bob,5200,2026-01-05 09:00,TRANSFER
EMPLOYER,bob,5200,2026-02-05 09:00,TRANSFER
bob,LANDLORD,1800,2026-02-06 09:00,TRANSFER
"""


def _client() -> TestClient:
    reset_department()
    from src.api.main import app
    return TestClient(app)


def test_benchmark_endpoint_is_gone():
    assert _client().get("/api/eval/public").status_code == 404


def test_typology_library_served():
    body = _client().get("/api/typologies").json()
    assert any(t["id"] == "typology/structuring" for t in body["typologies"])


def test_org_profile_roundtrip_and_history_baselines():
    client = _client()
    r = client.post("/api/org/profile", json={
        "name": "Acme Bank", "ctr_threshold": 10000,
        "watchlist": "OFFSHORE-1", "trusted_counterparties": ["EMPLOYER"]})
    assert r.status_code == 200 and r.json()["profile"]["watchlist"] == ["OFFSHORE-1"]

    h = client.post("/api/org/history",
                    files={"file": ("history.csv", HISTORY, "text/csv")})
    assert h.status_code == 200
    assert h.json()["baseline_accounts"] >= 2

    got = client.get("/api/org/profile").json()
    assert got["profile"]["name"] == "Acme Bank"
    assert got["baseline_accounts"] >= 2


def test_org_watchlist_shows_up_in_analysis_evidence():
    client = _client()
    client.post("/api/org/profile", json={"name": "Acme", "watchlist": "OFFSHORE-1"})
    r = client.post("/api/analyze?limit=1",
                    files={"file": ("ledger.csv", CSV, "text/csv")})
    evidence = r.json()["results"][0]["result"]["evidence"]
    assert any(e["source"] == "org:watchlist(OFFSHORE-1)" and e["verified"]
               for e in evidence)


def test_analysis_marks_suspicious_areas_of_the_dataset():
    client = _client()
    r = client.post("/api/analyze?limit=1",
                    files={"file": ("ledger.csv", CSV, "text/csv")})
    top = r.json()["results"][0]
    assert top["txns"], "transaction rows missing from the response"
    assert top["flagged_txns"], "no transactions were heat-marked"
    flagged_ids = set(top["flagged_txns"])
    assert flagged_ids <= {t["txn_id"] for t in top["txns"]}
    assert all(reasons for reasons in top["flagged_txns"].values())


def test_chat_answers_grounded_in_the_casebook():
    client = _client()

    empty = client.post("/api/chat", json={"question": "what have you found?"}).json()
    assert "empty" in empty["answer"].lower()

    client.post("/api/analyze?limit=1",
                files={"file": ("ledger.csv", CSV, "text/csv")})

    why = client.post("/api/chat", json={"question": "why was MULE-7 flagged?"}).json()
    assert "MULE-7" in why["answer"]
    assert "suspicious" in why["answer"].lower()
    assert why["facts"]["cases"][0]["account"] == "MULE-7"

    what = client.post("/api/chat", json={"question": "what is structuring?"}).json()
    assert "threshold" in what["answer"].lower()

    assert client.post("/api/chat", json={"question": "  "}).status_code == 422
