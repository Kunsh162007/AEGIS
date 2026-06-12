"""FeedbackLoop — captures every human approve/reject and uses it two ways (§8):
  (a) nudges the autonomy thresholds, and
  (b) writes the reviewed case into the knowledge base as retrievable precedent.

Honest framing: threshold tuning + precedent retrieval, NOT model retraining.
"""
from __future__ import annotations

from ..data.schema import CaseResult, Verdict
from ..knowledge import KnowledgeBase
from ..policy.autonomy import AutonomyPolicy


class FeedbackLoop:
    def __init__(self, policy: AutonomyPolicy, kb: KnowledgeBase, step: float = 0.02):
        self.policy = policy
        self.kb = kb
        self.step = step
        self.history: list[dict] = []

    def record(self, result: CaseResult, officer_decision: Verdict) -> dict:
        """officer_decision: the human's TRUE verdict for the escalated case."""
        agreed = (officer_decision == result.verdict)

        # (a) Tune thresholds. If the human cleared what we escalated, relax a touch;
        #     if the human found suspicious what we leaned benign, tighten.
        before = self.policy.clear_confidence
        if officer_decision == Verdict.BENIGN and result.verdict != Verdict.BENIGN:
            self.policy.clear_confidence = max(0.4, self.policy.clear_confidence - self.step)
        elif officer_decision == Verdict.SUSPICIOUS and result.verdict == Verdict.BENIGN:
            self.policy.clear_confidence = min(0.9, self.policy.clear_confidence + self.step)

        # (b) Store reviewed precedent for retrieval on similar future cases.
        precedent = (f"Reviewed precedent: case {result.case_id} judged "
                     f"{officer_decision.value} by a human officer. Key evidence: "
                     + "; ".join(e.claim for e in result.verified_evidence()[:2]))
        self.kb.add_precedent(f"precedent/{result.case_id}", precedent)

        entry = {"case_id": result.case_id, "agreed": agreed,
                 "officer_decision": officer_decision.value,
                 "clear_confidence_before": round(before, 3),
                 "clear_confidence_after": round(self.policy.clear_confidence, 3),
                 "precedent": precedent}
        self.history.append(entry)
        return entry
