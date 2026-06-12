"""BaseAgent — shared plumbing: a model client at the right tier, a handle to
the Band room, and helpers to post cited evidence to the case room.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from ..models.client import ModelClient


class BaseAgent:
    name: str = "agent"
    tier: str = "specialist"          # specialist | reasoning
    required_scope: str = ""          # credential-traversal scope this agent needs (§4)

    def __init__(self, model: ModelClient | None = None):
        self.model = model or ModelClient()

    def narrate(self, prompt: str, system: str = "", max_tokens: int = 512) -> str:
        return self.model.complete(prompt, tier=self.tier, agent=self.name, system=system,
                                   max_tokens=max_tokens)

    def _evidence(self, claim: str, source: str, weight: float,
                  supports: Verdict = Verdict.SUSPICIOUS) -> Evidence:
        return Evidence(agent=self.name, claim=claim, source=source, weight=weight,
                        supports=supports)

    def investigate(self, case: Case, room: CaseRoom) -> list[Evidence]:  # noqa: D401
        """Override. Must return a list of cited Evidence and post it to the room."""
        raise NotImplementedError

    def _guarded(self, case: Case, room: CaseRoom) -> bool:
        """Enforce credential traversal before touching data (§4)."""
        if self.required_scope and not room.require_scope(self.name, self.required_scope):
            return False
        return True
