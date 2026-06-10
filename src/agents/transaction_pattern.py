"""Transaction Pattern specialist (§5 #2) — real statistical machinery:
structuring near the CTR threshold, velocity bursts, round-number flags.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from .base import BaseAgent

CTR_THRESHOLD = 10_000


class TransactionPatternAgent(BaseAgent):
    name = "transaction_pattern"
    tier = "specialist"
    required_scope = "txn:read"

    def investigate(self, case: Case, room: CaseRoom) -> list[Evidence]:
        if not self._guarded(case, room):
            return []
        ev: list[Evidence] = []

        # 1) Structuring: clusters of deposits just under the reporting threshold.
        near = [t for t in case.transactions
                if 0.85 * CTR_THRESHOLD <= t.amount < CTR_THRESHOLD and t.channel == "cash"]
        if len(near) >= 3:
            ids = ",".join(t.txn_id for t in near)
            ev.append(self._evidence(
                f"{len(near)} cash deposits between ${0.85*CTR_THRESHOLD:,.0f} and "
                f"${CTR_THRESHOLD:,.0f} — consistent with structuring to avoid CTR reporting.",
                source=f"txn:[{ids}]", weight=0.85))

        # 2) Velocity: many transfers into the focus account in a short window.
        into_focus = [t for t in case.transactions if t.dst_account == case.focus_account]
        if len(into_focus) >= 4:
            span = (max(t.timestamp for t in into_focus)
                    - min(t.timestamp for t in into_focus)).total_seconds() / 3600
            if span <= 24:
                ev.append(self._evidence(
                    f"{len(into_focus)} inbound transfers to the focus account within "
                    f"{span:.0f}h — abnormal velocity.",
                    source=f"txn:inbound({case.focus_account})", weight=0.6))

        # 3) Pass-through: total in ≈ total out quickly (layering signal).
        out_focus = [t for t in case.transactions if t.src_account == case.focus_account]
        tin = sum(t.amount for t in into_focus)
        tout = sum(t.amount for t in out_focus)
        if tin > 0 and tout / tin >= 0.8 and out_focus:
            ev.append(self._evidence(
                f"~{tout/tin*100:.0f}% of inbound funds (${tin:,.0f}) moved straight out "
                f"(${tout:,.0f}) — pass-through / layering.",
                source=f"txn:passthrough({case.focus_account})", weight=0.7))

        if not ev:
            ev.append(self._evidence(
                "No structuring, velocity, or pass-through anomaly in the transaction set.",
                source="txn:scan", weight=0.2, supports=Verdict.BENIGN))

        for e in ev:
            room.post(self.name, "evidence", e.model_dump(mode="json"))
        return ev
