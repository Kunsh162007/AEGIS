"""Identity / KYC specialist (§5 #3) — actual behaviour vs expected profile,
plus synthetic sanctions/PEP context. Real machinery: profile-deviation math.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from .base import BaseAgent


class IdentityKycAgent(BaseAgent):
    name = "identity_kyc"
    tier = "specialist"
    required_scope = "kyc:read"

    def investigate(self, case: Case, room: CaseRoom) -> list[Evidence]:
        if not self._guarded(case, room):
            return []
        ev: list[Evidence] = []
        focus = case.party(case.focus_account)

        if focus:
            inbound = sum(t.amount for t in case.transactions
                          if t.dst_account == focus.account)
            expected = focus.expected_monthly_volume or 1.0
            ratio = inbound / expected
            if inbound == 0:
                ev.append(self._evidence(
                    "No inbound activity to the focus account in this case — "
                    "nothing to assess against the expected profile.",
                    source=f"kyc:profile({focus.account})", weight=0.15,
                    supports=Verdict.BENIGN))
            elif ratio >= 2.0:
                ev.append(self._evidence(
                    f"Inbound ${inbound:,.0f} is {ratio:.1f}x the account's expected "
                    f"monthly volume (${expected:,.0f}) — behaviour off profile.",
                    source=f"kyc:profile({focus.account})", weight=0.55))
            else:
                ev.append(self._evidence(
                    f"Inbound ${inbound:,.0f} is within ~{ratio:.1f}x expected profile "
                    f"(${expected:,.0f}) — consistent with normal behaviour.",
                    source=f"kyc:profile({focus.account})", weight=0.2,
                    supports=Verdict.BENIGN))

        for p in case.parties:
            if p.on_sanctions_list:
                ev.append(self._evidence(
                    f"Counterparty {p.account} appears on the (synthetic) sanctions list.",
                    source=f"kyc:sanctions({p.account})", weight=0.95))
            if p.is_pep:
                ev.append(self._evidence(
                    f"Counterparty {p.account} flagged as a politically exposed person.",
                    source=f"kyc:pep({p.account})", weight=0.5))

        for e in ev:
            room.post(self.name, "evidence", e.model_dump(mode="json"))
        return ev
