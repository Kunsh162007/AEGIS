"""Bring-your-own-data path: CSV -> cases -> investigation -> API."""
from __future__ import annotations

import pytest

from src.data.user_upload import cases_from_csv, parse_csv

MULE_CSV = b"""from,to,amount,date,type
a1,MULE-7,9400,2026-03-01 10:00,TRANSFER
a2,MULE-7,9100,2026-03-01 11:00,TRANSFER
a3,MULE-7,9700,2026-03-01 12:30,TRANSFER
a4,MULE-7,8900,2026-03-01 14:00,TRANSFER
a5,MULE-7,9300,2026-03-01 15:00,TRANSFER
MULE-7,OFFSHORE-1,45900,2026-03-01 18:00,TRANSFER
EMPLOYER,bob,5200,2026-03-05 09:00,TRANSFER
"""


def test_parse_csv_flexible_headers():
    edges = parse_csv(MULE_CSV)
    assert len(edges) == 7
    assert edges[0]["src"] == "a1" and edges[0]["dst"] == "MULE-7"
    assert edges[0]["channel"] == "transfer"
    assert edges[0]["ts"] is not None  # date column parsed


def test_parse_csv_missing_columns_is_clear_error():
    with pytest.raises(ValueError, match="missing required column"):
        parse_csv(b"foo,bar\n1,2\n")


def test_most_active_account_is_the_mule_and_flags_suspicious():
    from src.orchestrator import Orchestrator
    cases = cases_from_csv(MULE_CSV, limit=1)
    assert cases[0].focus_account == "MULE-7"
    assert cases[0].alert_type == "mule_network"
    assert cases[0].label is None  # no ground truth on user data
    res = Orchestrator().investigate(cases[0])
    assert res.verdict.value == "suspicious"


def test_focus_account_selection_and_unknown_focus():
    cases = cases_from_csv(MULE_CSV, focus="bob")
    assert [c.focus_account for c in cases] == ["bob"]
    with pytest.raises(ValueError, match="does not appear"):
        cases_from_csv(MULE_CSV, focus="nobody")


def test_excel_and_json_uploads():
    import io

    import pandas as pd

    from src.data.user_upload import cases_from_upload, parse_upload
    df = pd.read_csv(io.BytesIO(MULE_CSV))

    xlsx = io.BytesIO()
    df.to_excel(xlsx, index=False)
    edges = parse_upload(xlsx.getvalue(), "ledger.xlsx")
    assert len(edges) == 7

    js = df.to_json(orient="records").encode()
    cases = cases_from_upload(js, "ledger.json", limit=1)
    assert cases[0].focus_account == "MULE-7"


def test_unsupported_extension_is_clear_error():
    from src.data.user_upload import parse_upload
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_upload(b"whatever", "data.docx")


def test_unreadable_pdf_is_clear_error():
    from src.data.user_upload import parse_upload
    with pytest.raises(ValueError, match="Couldn't read this .pdf"):
        parse_upload(b"not a real pdf", "statement.pdf")


def test_analyze_endpoint():
    from fastapi.testclient import TestClient

    from src.api.main import app
    client = TestClient(app)
    r = client.post("/api/analyze?limit=1",
                    files={"file": ("ledger.csv", MULE_CSV, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["accounts_analyzed"] == 1
    top = body["results"][0]
    assert top["account"] == "MULE-7"
    assert top["result"]["verdict"] == "suspicious"

    bad = client.post("/api/analyze", files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert bad.status_code == 422
