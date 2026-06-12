"""Strategic Intelligence — the cross-case analyst: emerging typologies,
repeat subjects, bridge counterparties, consortium-safe descriptors."""
from __future__ import annotations

from src.agents.strategic_intel import StrategicIntelAgent


def _row(uid, account, alert, verdict, counterparties):
    return {"uid": uid, "account": account, "alert_type": alert,
            "verdict": verdict, "counterparties": counterparties}


def test_briefing_finds_patterns_no_single_case_can_see():
    rows = [
        _row("C1", "A1", "structuring", "suspicious", ["X9", "B2"]),
        _row("C2", "A2", "structuring", "suspicious", ["X9"]),
        _row("C3", "A3", "profile_anomaly", "benign", ["Z1"]),
        _row("C4", "A1", "layering", "uncertain", []),
    ]
    b = StrategicIntelAgent().brief(rows)

    assert b["cases_reviewed"] == 4 and b["cases_flagged"] == 3
    assert {"typology": "structuring", "cases": 2} in b["emerging_typologies"]
    assert any(s["account"] == "A1" for s in b["repeat_subjects"])
    link = next(l for l in b["cross_case_links"] if l["counterparty"] == "X9")
    assert set(link["links_cases"]) == {"C1", "C2"}   # the hidden bridge
    assert b["headline"]


def test_shareable_patterns_carry_no_records():
    rows = [_row(f"C{i}", f"A{i}", "structuring", "suspicious", ["X9"])
            for i in range(3)]
    b = StrategicIntelAgent().brief(rows)
    for p in b["shareable_patterns"]:
        assert set(p) == {"typology", "cases", "scope"}  # abstract only (§7)


def test_empty_casebook_is_calm():
    b = StrategicIntelAgent().brief([])
    assert b["cases_reviewed"] == 0
    assert b["emerging_typologies"] == []
    assert b["cross_case_links"] == []
