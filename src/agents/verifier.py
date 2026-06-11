"""Verifier / Evidence Auditor (§5 #7) — NO EVIDENCE, NO VERDICT.

Two rejection rules:
  1. Uncited claim — empty or unresolvable source → rejected outright.
  2. Rebutted claim — a suspicious claim fully accounted for by the Challenger's
     innocent explanation (and corroborated by benign evidence) → rejected.

Surviving claims get a per-claim confidence. This is the auditable core (§19.9).
"""
from __future__ import annotations

import re

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from .base import BaseAgent

_VALID_PREFIX = ("txn:", "graph:", "kb:", "kyc:")


class VerifierAgent(BaseAgent):
    name = "verifier"
    tier = "reasoning"

    def _is_cited(self, case: Case, ev: Evidence) -> bool:
        src = ev.source.strip()
        # Rule 1: no source, or not a recognised evidence prefix -> not cited.
        if not src or not src.startswith(_VALID_PREFIX):
            return False
        # Rule 1b: every record id cited in [] or () must actually exist in the
        # case — catches hallucinated references. All legitimate sources only
        # ever bracket txn ids or account ids (see the specialist agents), so a
        # single unknown token rejects the claim. Match the WHOLE comma-separated
        # reference (ids may contain hyphens, e.g. "010-8000EBD0"); don't split
        # inside an id.
        known = {t.txn_id for t in case.transactions} | {p.account for p in case.parties}
        bracketed = re.findall(r"[\[(]([^\])]+)[\])]", src)
        for chunk in bracketed:
            for part in chunk.split(","):
                part = part.strip()
                if part and part not in known:
                    return False
        return True

    def verify(self, case: Case, evidence: list[Evidence], challenge: dict,
               room: CaseRoom) -> tuple[list[Evidence], list[str]]:
        rejected: list[str] = []
        # Categories the Challenger raised a grounded innocent explanation against.
        targeted: set[str] = set()
        for r in challenge.get("rebuttals", []):
            targeted.update(r.get("targets", []))

        for ev in evidence:
            # Rule 1: citation check — no evidence, no verdict.
            if not self._is_cited(case, ev):
                ev.verified = False
                rejected.append(f"{ev.claim}  [REJECTED: uncited — {ev.source or 'no source'}]")
                continue
            # Rule 2: a suspicious claim whose source category is specifically
            # rebutted by a grounded innocent explanation is excluded.
            category = re.split(r"[\[(]", ev.source)[0]
            if (ev.supports == Verdict.SUSPICIOUS
                    and any(category.startswith(t) for t in targeted)):
                ev.verified = False
                rejected.append(f"{ev.claim}  [REJECTED: rebutted by innocent explanation]")
                continue
            ev.verified = True
            ev.confidence = round(min(0.99, ev.weight + 0.1), 2)

        for ev in evidence:
            room.post(self.name, "verify",
                      {"claim": ev.claim, "verified": ev.verified,
                       "confidence": ev.confidence, "source": ev.source})
        if rejected:
            room.post(self.name, "rejected", {"count": len(rejected), "claims": rejected})
        return evidence, rejected
