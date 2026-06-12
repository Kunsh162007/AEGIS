"""Case-management arithmetic — the case-manager analyst role: priority
scoring, SLA clocks, and the analyst-workload model behind the "one human runs
the department" numbers. Every assumption is an explicit constant surfaced
verbatim by /api/operations, never buried in prose.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..data.schema import Case, CaseResult, Verdict

# Blended manual effort per alert (L1 triage + L2 investigation). Industry
# studies put this at 30–60 min; we use the midpoint and SHOW the assumption.
MANUAL_MINUTES_PER_ALERT = 45.0
# Reviewing an AEGIS-prepared case: evidence chain, challenge, QA and draft SAR
# are already on the desk — the human only decides.
REVIEW_MINUTES_WITH_AEGIS = 10.0


def exposure(case: Case) -> float:
    """Money moved through the focus account — the value at risk."""
    return sum(t.amount for t in case.transactions
               if case.focus_account in (t.src_account, t.dst_account))


def priority_score(case: Case, result: CaseResult) -> float:
    """0–100. Verdict severity dominates; confidence, exposure, a consortium
    confirmation and open QA findings refine it."""
    base = {Verdict.SUSPICIOUS: 70.0, Verdict.UNCERTAIN: 40.0,
            Verdict.BENIGN: 10.0}[result.verdict]
    base += result.confidence * 15.0
    exp = exposure(case)
    if exp >= 1_000_000:
        base += 15.0
    elif exp >= 100_000:
        base += 10.0
    elif exp >= 10_000:
        base += 5.0
    if result.consortium_confirmation:
        base += 10.0
    if result.qa_findings:
        base += 5.0  # process doubts make a case MORE urgent to review, not less
    return round(min(100.0, base), 1)


def sla_due(priority: float, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    if priority >= 75:
        return now + timedelta(hours=24)
    if priority >= 50:
        return now + timedelta(hours=72)
    return now + timedelta(hours=168)


def hours_saved(auto_cleared: int, reviewed: int) -> float:
    """Manual baseline minus the residual human review time, in hours."""
    saved = (auto_cleared * MANUAL_MINUTES_PER_ALERT
             + reviewed * (MANUAL_MINUTES_PER_ALERT - REVIEW_MINUTES_WITH_AEGIS))
    return round(saved / 60.0, 1)
