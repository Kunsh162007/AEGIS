"""The human-in-the-loop feedback loop (§8/§12): a reviewed decision must tune
the autonomy threshold and store a retrievable precedent."""
from __future__ import annotations

from src.data.schema import CaseResult, Evidence, Verdict
from src.feedback import FeedbackLoop
from src.knowledge import KnowledgeBase
from src.policy.autonomy import AutonomyPolicy


def _result() -> CaseResult:
    return CaseResult(
        case_id="C1", verdict=Verdict.SUSPICIOUS,
        evidence=[Evidence(agent="network_graph", claim="mule hub",
                           source="graph:hub(ACC1)", weight=0.8, verified=True,
                           confidence=0.9)])


def test_human_clear_relaxes_threshold_and_stores_precedent():
    policy, kb = AutonomyPolicy(), KnowledgeBase()
    loop = FeedbackLoop(policy, kb)
    before = policy.clear_confidence

    entry = loop.record(_result(), officer_decision=Verdict.BENIGN)

    assert policy.clear_confidence < before              # cleared what we escalated -> relax
    assert entry["agreed"] is False
    assert any(d["id"] == "precedent/C1" for d in kb.docs)  # precedent retrievable


def test_human_confirms_suspicious_tightens_threshold():
    policy, kb = AutonomyPolicy(), KnowledgeBase()
    loop = FeedbackLoop(policy, kb)
    res = _result()
    res.verdict = Verdict.BENIGN
    before = policy.clear_confidence

    loop.record(res, officer_decision=Verdict.SUSPICIOUS)

    assert policy.clear_confidence > before              # missed a real one -> tighten
