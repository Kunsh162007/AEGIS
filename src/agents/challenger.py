"""Challenger / Red-Team (§5 #6) — actively argues the INNOCENT explanation.
A suspicion that survives this is far likelier to be real (§2). The single
biggest lever against false positives.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from .base import BaseAgent

# Benign explanations the Challenger looks for, keyed on transaction-note keywords.
# Each `targets` a claim-source category it specifically rebuts (e.g. a profile
# anomaly) — it does NOT blanket-clear graph/structuring evidence (§ targeted rebuttal).
INNOCENT_EXPLANATIONS = {
    "bonus": {"explanation": "Large credit references payroll/bonus from a business "
              "account — consistent with legitimate salary.", "targets": ["kyc:profile"]},
    "payroll": {"explanation": "Credit references payroll — legitimate salary income.",
                "targets": ["kyc:profile"]},
    "property": {"explanation": "Large credit references property completion from a "
                 "conveyancer — a lawful one-off, not layering.", "targets": ["kyc:profile"]},
    "completion": {"explanation": "Funds reference a property completion — lawful "
                   "conveyancing.", "targets": ["kyc:profile"]},
}


class ChallengerAgent(BaseAgent):
    name = "challenger"
    tier = "reasoning"

    def challenge(self, case: Case, evidence: list[Evidence], room: CaseRoom) -> dict:
        rebuttals: list[dict] = []

        # Find innocent explanations grounded in the transaction notes.
        notes = " ".join(t.note.lower() for t in case.transactions)
        seen_targets: set[str] = set()
        for kw, spec in INNOCENT_EXPLANATIONS.items():
            if kw in notes:
                rebuttals.append({"explanation": spec["explanation"],
                                  "source": f"txn:note~{kw}", "targets": spec["targets"]})
                seen_targets.update(spec["targets"])

        # Single-transaction "anomalies" are weak: one big legal credit is common —
        # this rebuts a profile anomaly, not graph/structuring evidence.
        if len(case.transactions) == 1:
            rebuttals.append({
                "explanation": "The alert rests on a single transaction; one large "
                               "credit alone is a weak basis for suspicion.",
                "source": "txn:count=1", "targets": ["kyc:profile"]})

        argument = self.narrate(
            f"Argue the innocent explanation for case {case.case_id}. "
            f"Rebuttals: {[r['explanation'] for r in rebuttals]}",
            system="You are a red-team analyst trying to clear the customer.")

        room.post(self.name, "challenge", {"argument": argument, "rebuttals": rebuttals})
        return {"argument": argument, "rebuttals": rebuttals}
