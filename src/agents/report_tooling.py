"""Report / Tooling agent (§5 #9) — drafts the case report for escalated cases
in the shape a real filing takes: a FinCEN-style SAR with subject information,
activity characterisation, a five-Ws narrative, and the full verified evidence
chain as the appendix. Everything is computed from the case; the officer signs,
the agent never files. (Codeband in production; framework-agnostic here.)
"""
from __future__ import annotations

from ..data.schema import Case, CaseResult
from .base import BaseAgent


class ReportAgent(BaseAgent):
    name = "report_tooling"
    tier = "specialist"

    def draft_report(self, case: Case, result: CaseResult) -> str:
        focus = case.transactions and [
            t for t in case.transactions
            if case.focus_account in (t.src_account, t.dst_account)] or []
        total = sum(t.amount for t in focus)
        dates = sorted(t.timestamp for t in focus) if focus else []
        counterparties = sorted({
            (t.dst_account if t.src_account == case.focus_account else t.src_account)
            for t in focus} - {case.focus_account})
        party = case.party(case.focus_account)

        lines = [
            f"# DRAFT SUSPICIOUS ACTIVITY REPORT — {case.case_id}",
            "_Prepared by AEGIS for compliance-officer review. "
            "Not filed until a human signs._",
            "",
            "## Part I — Subject information",
            f"- Account: {case.focus_account}"
            + (f" ({party.account_type}, {party.country})" if party else ""),
            f"- Known counterparties in scope: {len(counterparties)}",
            "",
            "## Part II — Suspicious activity information",
            f"- Characterisation: {case.alert_type}",
            f"- Amount involved: ${total:,.2f} across {len(focus)} transaction(s)",
        ]
        if dates:
            lines.append(f"- Activity window: {dates[0]:%Y-%m-%d} to {dates[-1]:%Y-%m-%d}")
        lines += [
            f"- AEGIS verdict: {result.verdict.value} "
            f"(confidence {result.confidence})"
            + (f" · QA score {result.qa_score}" if result.qa_score is not None else ""),
            "",
            "## Part III — Narrative",
            f"WHO: account {case.focus_account}"
            + (f", transacting with {', '.join(counterparties[:5])}"
               + ("…" if len(counterparties) > 5 else "") if counterparties else "") + ".",
            f"WHAT: activity consistent with {case.alert_type}; "
            f"${total:,.2f} moved through the account.",
            (f"WHEN: between {dates[0]:%Y-%m-%d %H:%M} and {dates[-1]:%Y-%m-%d %H:%M}."
             if dates else "WHEN: see transaction appendix."),
            "WHERE: channels observed — "
            + ", ".join(sorted({t.channel for t in focus})) + "." if focus else "",
            "WHY SUSPICIOUS: " + (result.rationale or "see verified evidence below."),
            "",
            "## Appendix A — Verified evidence chain",
        ]
        for e in result.verified_evidence():
            lines.append(f"- {e.claim}  _(source: {e.source}, confidence: {e.confidence})_")
        if result.rejected_claims:
            lines += ["", "## Appendix B — Claims rejected during verification "
                          "(excluded from this report)"]
            lines += [f"- {c}" for c in result.rejected_claims]
        if result.consortium_confirmation:
            lines += ["", "## Appendix C — Consortium confirmation (pattern-only)",
                      f"- {result.consortium_confirmation}"]
        lines += ["", "## Appendix D — Adversarial review",
                  result.challenger_argument or "—"]
        if result.qa_findings:
            lines += ["", "## Appendix E — QA findings",
                      *[f"- {f}" for f in result.qa_findings]]

        report = "\n".join(lines)
        result.report = report
        return report
