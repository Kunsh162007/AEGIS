"""Report / Tooling agent (§5 #9) — drafts the evidence-cited case report / SAR
for escalated cases. (Codeband in production; framework-agnostic here.)
"""
from __future__ import annotations

from ..data.schema import Case, CaseResult
from .base import BaseAgent


class ReportAgent(BaseAgent):
    name = "report_tooling"
    tier = "specialist"

    def draft_report(self, case: Case, result: CaseResult) -> str:
        lines = [
            f"# Suspicious Activity Case Report — {case.case_id}",
            f"**Verdict:** {result.verdict.value}  |  **Confidence:** {result.confidence}",
            f"**Decision:** {result.decision.value}",
            f"**Alert type:** {case.alert_type}  |  **Focus account:** {case.focus_account}",
            "",
            "## Evidence chain (verified claims only)",
        ]
        for e in result.verified_evidence():
            lines.append(f"- {e.claim}  _(source: {e.source}, confidence: {e.confidence})_")
        if result.rejected_claims:
            lines += ["", "## Rejected during verification (excluded from the verdict)"]
            lines += [f"- {c}" for c in result.rejected_claims]
        if result.consortium_confirmation:
            lines += ["", "## Consortium", f"- {result.consortium_confirmation}"]
        lines += ["", "## Challenger (innocent-explanation review)", result.challenger_argument or "—",
                  "", "## Rationale", result.rationale]
        report = "\n".join(lines)
        result.report = report
        return report
