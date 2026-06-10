"""Intake & Orchestrator (§5 #1) — opens the case room and decides which
specialists to recruit for this alert type (dynamic recruitment, §6)."""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case
from .base import BaseAgent

# Which specialists matter for which alert type (dynamic recruitment).
RECRUITMENT = {
    "structuring": ["transaction_pattern", "network_graph", "external_intel"],
    "mule_network": ["transaction_pattern", "network_graph", "external_intel"],
    "layering": ["transaction_pattern", "network_graph", "external_intel"],
    "profile_anomaly": ["transaction_pattern", "identity_kyc", "external_intel"],
    "adverse_media": ["identity_kyc", "external_intel", "network_graph"],
}


class IntakeAgent(BaseAgent):
    name = "intake"
    tier = "reasoning"

    def recruit_for(self, case: Case, room: CaseRoom) -> list[str]:
        roles = RECRUITMENT.get(case.alert_type, ["transaction_pattern", "network_graph",
                                                  "identity_kyc", "external_intel"])
        for role in roles:
            room.recruit(role)
        room.post(self.name, "plan", {"alert_type": case.alert_type, "recruited": roles})
        return roles
