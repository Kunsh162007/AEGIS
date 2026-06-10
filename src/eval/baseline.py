"""The HONEST baseline (§9): a single-pass risk scorer with the SAME data access
as AEGIS but NO adversarial challenge and NO evidence verification — i.e. 'one
model guessing once'. It is deliberately reasonable, not a strawman: it uses real
signals. Its weakness is structural — with no Challenger to surface the innocent
explanation, it over-flags benign-but-unusual activity (the false positives AEGIS
removes).
"""
from __future__ import annotations

from ..data.schema import Case, Verdict


def baseline_verdict(case: Case) -> Verdict:
    score = 0.0

    # Signal 1: any large transaction (a naive scorer treats size as risk).
    if any(t.amount >= 15_000 for t in case.transactions):
        score += 0.5
    # Signal 2: many deposits near the reporting threshold.
    near = [t for t in case.transactions if 8_000 <= t.amount < 10_000]
    if len(near) >= 3:
        score += 0.5
    # Signal 3: high inbound velocity to the focus account.
    inbound = [t for t in case.transactions if t.dst_account == case.focus_account]
    if len(inbound) >= 4:
        score += 0.3
    # Signal 4: off-profile inbound — the single-pass model has no way to *clear*
    # this with an innocent explanation, so it counts against the customer.
    focus = case.party(case.focus_account)
    if focus and focus.expected_monthly_volume:
        if sum(t.amount for t in inbound) >= 2 * focus.expected_monthly_volume:
            score += 0.4

    return Verdict.SUSPICIOUS if score >= 0.5 else Verdict.BENIGN
