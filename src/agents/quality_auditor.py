"""Quality Auditor (agent #11) — the QA / supervisory reviewer every real FIU
staffs. Runs AFTER adjudication and audits the *process*, not the data: were
all verified claims actually cited, did the Challenger engage, does the verdict
follow from the surviving evidence, did anything rejected leak back in.

Its one power is the one a human QA supervisor has: an auto-clear that fails a
critical control is never allowed to stand — it is overridden to escalation.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, CaseResult, Decision, Verdict
from .base import BaseAgent

_VALID_PREFIX = ("txn:", "graph:", "kb:", "kyc:")
_HIGH_WEIGHT = 0.7


class QualityAuditorAgent(BaseAgent):
    name = "quality_auditor"
    tier = "reasoning"

    def audit(self, case: Case, result: CaseResult, room: CaseRoom) -> CaseResult:
        verified = result.verified_evidence()
        # (finding-if-failed, passed, critical)
        checks: list[tuple[str, bool, bool]] = []

        uncited = [e for e in verified
                   if not e.source.strip().startswith(_VALID_PREFIX)]
        checks.append((f"{len(uncited)} verified claim(s) carry no recognised "
                       "evidence source", not uncited, True))

        checks.append(("the Challenger never argued the innocent explanation",
                       bool(result.challenger_argument.strip()), False))

        if result.verdict == Verdict.SUSPICIOUS:
            supported = any(e.supports == Verdict.SUSPICIOUS for e in verified)
            checks.append(("suspicious verdict rests on zero verified "
                           "suspicious claims", supported, True))
        if result.verdict == Verdict.BENIGN:
            heavy = [e for e in verified
                     if e.supports == Verdict.SUSPICIOUS and e.weight >= _HIGH_WEIGHT]
            checks.append((f"benign verdict despite {len(heavy)} high-weight "
                           "verified suspicious claim(s)", not heavy, True))

        leaked = [e.claim for e in verified
                  if any(e.claim in r for r in result.rejected_claims)]
        checks.append((f"{len(leaked)} claim(s) the Verifier rejected leaked "
                       "back into the verdict", not leaked, True))

        checks.append(("decision recorded without a rationale",
                       bool(result.rationale.strip()), False))

        failed = [(finding, critical) for finding, ok, critical in checks if not ok]
        result.qa_score = round((len(checks) - len(failed)) / len(checks), 2)
        result.qa_findings = [finding for finding, _ in failed]

        overridden = False
        if result.decision == Decision.AUTO_CLEAR and any(c for _, c in failed):
            result.decision = Decision.ESCALATE
            result.rationale += (" [QA override: auto-clear blocked — "
                                 + "; ".join(result.qa_findings) + "]")
            overridden = True

        room.post(self.name, "qa", {
            "case_id": result.case_id, "qa_score": result.qa_score,
            "checks_passed": len(checks) - len(failed),
            "checks_total": len(checks), "findings": result.qa_findings,
            "auto_clear_overridden": overridden})
        return result
