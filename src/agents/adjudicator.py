"""Adjudicator (§5 #8) — synthesises the VERIFIED evidence into a verdict +
confidence + evidence chain, then applies the risk-based autonomy policy (§8).
Only verified claims count — rejected claims carry zero weight.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, CaseResult, Evidence, Verdict
from ..policy.autonomy import AutonomyPolicy
from .base import BaseAgent


class AdjudicatorAgent(BaseAgent):
    name = "adjudicator"
    tier = "reasoning"

    def __init__(self, model=None, policy: AutonomyPolicy | None = None):
        super().__init__(model)
        self.policy = policy or AutonomyPolicy()

    def adjudicate(self, case: Case, evidence: list[Evidence], challenge: dict,
                   rejected: list[str], room: CaseRoom,
                   consortium_note: str | None = None) -> CaseResult:
        verified = [e for e in evidence if e.verified]
        sus = sum(e.weight for e in verified if e.supports == Verdict.SUSPICIOUS)
        ben = sum(e.weight for e in verified if e.supports == Verdict.BENIGN)
        if consortium_note:
            sus += 0.25  # a peer confirmation strengthens the suspicion (§7)

        total = sus + ben
        score = sus / total if total else 0.0  # 0..1 suspicion score

        if score >= 0.6 and sus >= 0.7:
            verdict = Verdict.SUSPICIOUS
        elif score <= 0.35:
            verdict = Verdict.BENIGN
        else:
            verdict = Verdict.UNCERTAIN
        confidence = round(abs(score - 0.5) * 2, 2)  # distance from the fence

        decision, rationale = self.policy.decide(verdict, confidence, sus)

        result = CaseResult(
            case_id=case.case_id, verdict=verdict, confidence=confidence,
            decision=decision, rationale=rationale, evidence=evidence,
            challenger_argument=challenge.get("argument", ""),
            rejected_claims=rejected, consortium_confirmation=consortium_note)

        room.post(self.name, "verdict", {
            "verdict": verdict.value, "confidence": confidence,
            "decision": decision.value, "rationale": rationale,
            "suspicion_score": round(score, 2),
            "verified_claims": len(verified), "rejected_claims": len(rejected)})
        return result
