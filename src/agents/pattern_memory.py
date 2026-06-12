"""Pattern Memory (agent #14) — the institutional memory. This is the agent
that makes AEGIS measurably better with every analysis:

  * if the officer previously CONFIRMED a case with this exact structural
    signature, that judgment is evidence on the next one;
  * if the officer previously DISMISSED it, that is exculpatory evidence —
    the same false positive doesn't get raised twice;
  * a repeat subject (this account confirmed suspicious before) is flagged;
  * suspicious structure matching NO library typology is flagged as a
    potentially NOVEL pattern for the intelligence briefing.

All lookups hit the persistent casebook; nothing is remembered in-process.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..casework.patterns import looks_novel, signature
from ..data.schema import Case, Evidence, Verdict
from .base import BaseAgent


class PatternMemoryAgent(BaseAgent):
    name = "pattern_memory"
    tier = "reasoning"

    def __init__(self, model=None, store=None):
        super().__init__(model)
        self.store = store

    def investigate(self, case: Case, room: CaseRoom) -> list[Evidence]:
        if self.store is None:
            return []
        ev: list[Evidence] = []
        sig = signature(case)

        prior = self.store.match_patterns(sig)
        confirmed = [p for p in prior if p["outcome"] == "confirmed_suspicious"]
        dismissed = [p for p in prior if p["outcome"] == "dismissed_false_positive"]
        if confirmed:
            ev.append(self._evidence(
                f"This activity's structural signature matches {len(confirmed)} "
                "prior case(s) the compliance officer CONFIRMED as suspicious "
                f"(e.g. {confirmed[0]['case_uid']}).",
                source=f"memory:pattern/{confirmed[0]['case_uid']}", weight=0.6))
        elif dismissed:
            ev.append(self._evidence(
                f"The same structural signature was previously reviewed and "
                f"DISMISSED as a false positive {len(dismissed)} time(s) "
                f"(e.g. {dismissed[0]['case_uid']}) — innocent precedent.",
                source=f"memory:pattern/{dismissed[0]['case_uid']}", weight=0.5,
                supports=Verdict.BENIGN))

        repeat = [c for c in self.store.prior_cases_for_account(case.focus_account)
                  if c["status"] == "confirmed_suspicious"]
        if repeat:
            ev.append(self._evidence(
                f"Account {case.focus_account} was CONFIRMED suspicious before "
                f"in {repeat[0]['uid']} ({repeat[0]['alert_type']}) — repeat subject.",
                source=f"memory:case/{repeat[0]['uid']}", weight=0.8))

        if looks_novel(sig):
            ev.append(self._evidence(
                "Laundering-shaped structure that matches NO library typology — "
                "flagged as a potentially novel pattern for the intelligence desk.",
                source="memory:novel", weight=0.4))

        for e in ev:
            room.post(self.name, "evidence", e.model_dump(mode="json"))
        return ev
