"""The Quality Auditor — the supervisory QA control: scores process integrity
on every finished case and blocks auto-clears that fail a critical check."""
from __future__ import annotations

from src.agents.quality_auditor import QualityAuditorAgent
from src.band import LocalMesh
from src.band.interface import Credential
from src.data.schema import CaseResult, Decision, Evidence, Verdict
from fixtures import case_structuring


def _room(case):
    return LocalMesh().open_room(case.case_id,
                                 Credential(officer_id="o", scopes={"*"}))


def _evidence(case, supports=Verdict.SUSPICIOUS, weight=0.85):
    return Evidence(agent="transaction_pattern", claim="structuring cluster",
                    source=f"txn:[{case.transactions[0].txn_id}]", weight=weight,
                    supports=supports, verified=True, confidence=0.9)


def test_clean_case_passes_all_checks():
    case = case_structuring()
    result = CaseResult(case_id=case.case_id, verdict=Verdict.SUSPICIOUS,
                        confidence=0.8, decision=Decision.ESCALATE,
                        rationale="escalated", challenger_argument="considered",
                        evidence=[_evidence(case)])
    out = QualityAuditorAgent().audit(case, result, _room(case))
    assert out.qa_score == 1.0
    assert out.qa_findings == []
    assert out.decision == Decision.ESCALATE


def test_unsafe_auto_clear_is_overridden_to_escalation():
    # A benign auto-clear sitting on a verified HIGH-WEIGHT suspicious claim
    # fails a critical control — QA must refuse to let it stand.
    case = case_structuring()
    result = CaseResult(case_id=case.case_id, verdict=Verdict.BENIGN,
                        confidence=0.9, decision=Decision.AUTO_CLEAR,
                        rationale="auto-cleared", challenger_argument="x",
                        evidence=[_evidence(case)])
    out = QualityAuditorAgent().audit(case, result, _room(case))
    assert out.decision == Decision.ESCALATE
    assert out.qa_findings
    assert "QA override" in out.rationale


def test_uncited_verified_claim_is_flagged():
    case = case_structuring()
    bad = _evidence(case)
    bad.source = "trust me"
    result = CaseResult(case_id=case.case_id, verdict=Verdict.SUSPICIOUS,
                        confidence=0.8, decision=Decision.ESCALATE,
                        rationale="escalated", challenger_argument="x",
                        evidence=[bad])
    out = QualityAuditorAgent().audit(case, result, _room(case))
    assert out.qa_score < 1.0
    assert any("no recognised" in f for f in out.qa_findings)


def test_pipeline_attaches_qa_score_to_every_result():
    from src.orchestrator import Orchestrator
    res = Orchestrator().investigate(case_structuring())
    assert res.qa_score is not None
