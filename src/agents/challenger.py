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


# An innocent explanation may only clear *soft, behavioural* flags (a profile
# anomaly). It must NEVER wave away structural laundering evidence (mule hubs,
# cycles, pass-through, structuring) — those are the fingerprints that survive
# the strongest innocent story. This cap protects recall when the LLM is on.
_REBUTTABLE_CATEGORIES = ["kyc:profile"]


class ChallengerAgent(BaseAgent):
    name = "challenger"
    tier = "reasoning"

    def challenge(self, case: Case, evidence: list[Evidence], room: CaseRoom) -> dict:
        rebuttals: list[dict] = []

        # Find innocent explanations grounded in the transaction notes.
        notes = " ".join(t.note.lower() for t in case.transactions)
        for kw, spec in INNOCENT_EXPLANATIONS.items():
            if kw in notes:
                rebuttals.append({"explanation": spec["explanation"],
                                  "source": f"txn:note~{kw}", "targets": spec["targets"]})

        # Single-transaction "anomalies" are weak: one big legal credit is common —
        # this rebuts a profile anomaly, not graph/structuring evidence.
        if len(case.transactions) == 1:
            rebuttals.append({
                "explanation": "The alert rests on a single transaction; one large "
                               "credit alone is a weak basis for suspicion.",
                "source": "txn:count=1", "targets": ["kyc:profile"]})

        # LLM-proposed innocent explanations (AI/ML API reasoning tier). These
        # GENERALISE the hardcoded keyword list to any legitimate narrative the
        # transaction notes support — the single biggest false-positive lever on
        # real data. Constrained to soft categories; the Verifier still requires
        # the rebuttal to be grounded, so the LLM can't fabricate a clearance.
        rebuttals.extend(self._llm_innocent_explanations(case, evidence))

        argument = self.narrate(
            f"Argue the innocent explanation for case {case.case_id}. "
            f"Rebuttals: {[r['explanation'] for r in rebuttals]}",
            system="You are a red-team analyst trying to clear the customer.")

        room.post(self.name, "challenge", {"argument": argument, "rebuttals": rebuttals})
        return {"argument": argument, "rebuttals": rebuttals}

    def _llm_innocent_explanations(self, case: Case, evidence: list[Evidence]) -> list[dict]:
        """Ask the reasoning model for a plausible legitimate explanation of the
        flagged behaviour. Returns [] in mock mode or on any failure (so the
        deterministic offline path is unchanged)."""
        if getattr(self.model, "provider", "mock") == "mock":
            return []  # offline/mock: keep the deterministic keyword behaviour
        try:
            notes = "; ".join(t.note for t in case.transactions[:8] if t.note)
            flagged = [e.claim for e in evidence
                       if e.supports == Verdict.SUSPICIOUS][:6]
            out = self.narrate(
                f"Transaction notes: {notes or '(none)'}\n"
                f"Flagged concerns: {flagged}\n"
                "If a plausible LEGITIMATE explanation fits the customer's behaviour "
                "(e.g. salary/bonus, property sale, inheritance, loan drawdown, "
                "business revenue, refund), give it in ONE sentence. If the activity "
                "has no innocent explanation, reply with exactly: NONE",
                system="You are a meticulous red-team AML analyst. Be terse and concrete.")
            text = out.strip()
            # Ignore "no explanation", and ignore mock/fallback narration (the
            # mock client prefixes every reply with "[<agent>] ") so an auto-mode
            # run with no working key can't inject a bogus clearance.
            if not text or text.upper().startswith("NONE") or text.startswith(f"[{self.name}]"):
                return []
            return [{"explanation": text[:300], "source": "llm:reasoning",
                     "targets": list(_REBUTTABLE_CATEGORIES)}]
        except Exception:
            return []
