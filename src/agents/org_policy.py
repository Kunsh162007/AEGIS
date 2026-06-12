"""Org Policy specialist (agent #13) — the in-house compliance analyst. Applies
the COMPANY'S OWN context to the case: its watchlist, its vetted
counterparties, its reporting threshold, and the account's own historical
baseline (built from the org's previous data). This is what makes two banks
running AEGIS get different — personalised — answers on the same file.

Only runs when an org profile or baselines exist; without them AEGIS is
unchanged.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from .base import BaseAgent


class OrgPolicyAgent(BaseAgent):
    name = "org_policy"
    tier = "specialist"
    required_scope = "kyc:read"

    def __init__(self, model=None, org: dict | None = None, store=None):
        super().__init__(model)
        self.org = org or {}
        self.store = store

    def investigate(self, case: Case, room: CaseRoom) -> list[Evidence]:
        if not self._guarded(case, room):
            return []
        ev: list[Evidence] = []
        accounts = {p.account for p in case.parties}

        # 1) Watchlist: the org already distrusts these accounts.
        for acct in sorted(set(self.org.get("watchlist", [])) & accounts):
            ev.append(self._evidence(
                f"Account {acct} is on the organisation's internal watchlist.",
                source=f"org:watchlist({acct})", weight=0.8))

        # 2) Trusted counterparties: vetted relationships are exculpatory for
        #    the flows that involve them.
        trusted = set(self.org.get("trusted_counterparties", [])) & accounts
        for acct in sorted(trusted - {case.focus_account}):
            n = sum(1 for t in case.transactions
                    if acct in (t.src_account, t.dst_account))
            if n:
                ev.append(self._evidence(
                    f"{n} transaction(s) involve {acct}, a counterparty the "
                    "organisation has vetted as trusted.",
                    source=f"org:trusted({acct})", weight=0.5,
                    supports=Verdict.BENIGN))

        # 3) The org's own reporting threshold (may differ from the $10k CTR).
        thr = float(self.org.get("ctr_threshold", 10_000.0) or 10_000.0)
        if thr and thr != 10_000.0:
            near = [t for t in case.transactions
                    if t.channel == "cash" and 0.85 * thr <= t.amount < thr]
            if len(near) >= 3:
                ids = ",".join(t.txn_id for t in near)
                ev.append(self._evidence(
                    f"{len(near)} cash deposits just under the organisation's "
                    f"OWN reporting threshold (${thr:,.0f}) — structuring "
                    "against the internal policy line.",
                    source=f"txn:[{ids}]", weight=0.85))

        # 4) The account's own history: deviation from ITS baseline, not an
        #    abstract norm. Built from the org's previously uploaded data.
        baseline = self.store.get_baseline(case.focus_account) if self.store else None
        if baseline and baseline["monthly_in"] > 0:
            inbound = sum(t.amount for t in case.transactions
                          if t.dst_account == case.focus_account)
            ratio = inbound / baseline["monthly_in"]
            if ratio >= 3.0:
                ev.append(self._evidence(
                    f"Inbound volume ${inbound:,.0f} is {ratio:.1f}× this "
                    f"account's OWN historical monthly baseline "
                    f"(${baseline['monthly_in']:,.0f}).",
                    source=f"org:baseline({case.focus_account})", weight=0.6))
            elif ratio <= 1.5:
                ev.append(self._evidence(
                    f"Inbound volume ${inbound:,.0f} is consistent with this "
                    f"account's historical baseline "
                    f"(${baseline['monthly_in']:,.0f}/month).",
                    source=f"org:baseline({case.focus_account})", weight=0.45,
                    supports=Verdict.BENIGN))
            new_partners = ({t.src_account for t in case.transactions
                             if t.dst_account == case.focus_account}
                            - set(baseline["top_counterparties"])
                            - {case.focus_account})
            if baseline["top_counterparties"] and len(new_partners) >= 4:
                ev.append(self._evidence(
                    f"{len(new_partners)} inbound counterparties never seen in "
                    "this account's history — relationship pattern shift.",
                    source=f"org:baseline({case.focus_account})", weight=0.4))

        for e in ev:
            room.post(self.name, "evidence", e.model_dump(mode="json"))
        return ev
