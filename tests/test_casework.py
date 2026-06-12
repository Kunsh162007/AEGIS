"""The department layer: persistent casebook, priority/SLA model, officer
decisions tuning the shared policy, and the operations KPIs."""
from __future__ import annotations

import pytest

from src.casework import Department
from src.casework.priority import hours_saved
from src.data.synthetic import case_salary_spike, case_structuring


def _dept() -> Department:
    return Department(db_path=":memory:")


def test_case_filed_with_priority_and_sla():
    dept = _dept()
    case = case_structuring()
    result = dept.orchestrator().investigate(case)
    row = dept.record_case(case, result, "ledger.csv")

    assert row["status"] == "pending_review"          # structuring escalates
    assert row["priority"] >= 70                      # suspicious dominates
    assert row["sla_due"]                             # review clock started
    stored = dept.store.get(row["uid"])
    assert stored["result"]["verdict"] == result.verdict.value
    assert stored["counterparties"]                   # for cross-case intel


def test_officer_decision_tunes_policy_and_closes_case():
    dept = _dept()
    case = case_structuring()
    result = dept.orchestrator().investigate(case)
    row = dept.record_case(case, result, "ledger.csv")
    before = dept.policy.clear_confidence

    out = dept.decide(row["uid"], "dismiss")          # human: false positive

    assert out["status"] == "dismissed_false_positive"
    assert dept.policy.clear_confidence < before      # threshold relaxed
    assert dept.store.get(row["uid"])["status"] == "dismissed_false_positive"
    assert dept.store.feedback_history()
    assert dept.store.precedents()                    # precedent persisted
    with pytest.raises(ValueError):                   # no double decisions
        dept.decide(row["uid"], "confirm")


def test_learned_state_survives_restart(tmp_path):
    db = str(tmp_path / "aegis.db")
    dept = Department(db_path=db)
    case = case_structuring()
    row = dept.record_case(case, dept.orchestrator().investigate(case), "l.csv")
    dept.decide(row["uid"], "dismiss")
    tuned = dept.policy.clear_confidence

    reopened = Department(db_path=db)                 # simulated restart
    assert reopened.policy.clear_confidence == tuned
    assert any(d["id"].startswith("precedent/") for d in reopened.kb.docs)
    assert reopened.store.get(row["uid"])["status"] == "dismissed_false_positive"


def test_operations_kpis():
    dept = _dept()
    for case in (case_structuring(), case_salary_spike()):
        dept.record_case(case, dept.orchestrator().investigate(case), "x.csv")
    ops = dept.operations()

    assert ops["cases_total"] == 2
    assert ops["pending_review"] + ops["auto_cleared"] == 2
    assert 0 <= ops["auto_clear_rate"] <= 1
    assert ops["analyst_hours_saved"] >= 0
    assert ops["workload_assumptions"]["manual_minutes_per_alert"] > 0
    assert ops["policy"]["clear_confidence"] == dept.policy.clear_confidence


def test_hours_saved_model_is_explicit():
    assert hours_saved(0, 0) == 0.0
    assert hours_saved(4, 0) == 3.0    # 4 alerts × 45 min fully automated
    assert hours_saved(0, 6) == 3.5    # 6 reviews × (45 − 10) min prepared
