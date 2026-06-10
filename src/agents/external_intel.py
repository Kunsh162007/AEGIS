"""External Intelligence specialist (§5 #5) — RAG over the typology / adverse-
media knowledge base. Real machinery: retrieval against the KnowledgeBase.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from ..knowledge import KnowledgeBase
from .base import BaseAgent


class ExternalIntelAgent(BaseAgent):
    name = "external_intel"
    tier = "specialist"
    required_scope = "kb:read"

    def __init__(self, model=None, kb: KnowledgeBase | None = None):
        super().__init__(model)
        self.kb = kb or KnowledgeBase()

    def investigate(self, case: Case, room: CaseRoom) -> list[Evidence]:
        if not self._guarded(case, room):
            return []
        # Build a retrieval query from the alert + a few transaction notes.
        notes = " ".join(t.note for t in case.transactions[:5])
        query = f"{case.alert_type} {notes}"
        hits = self.kb.retrieve(query, k=2)

        ev: list[Evidence] = []
        for h in hits:
            benign = h["id"].startswith("benign/")
            ev.append(self._evidence(
                f"Knowledge base match: {h['text'][:160]}",
                source=f"kb:{h['id']}", weight=0.3 if benign else 0.55,
                supports=Verdict.BENIGN if benign else Verdict.SUSPICIOUS))

        for e in ev:
            room.post(self.name, "evidence", e.model_dump(mode="json"))
        return ev
