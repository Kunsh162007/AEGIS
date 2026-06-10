"""AutonomyPolicy — the explicit, configurable, auditable rule that lets AEGIS
'think, decide, act independently' (§8): auto-clear confidently-benign cases,
escalate everything consequential or uncertain. Thresholds are tunable by the
feedback loop (§12 #16).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..data.schema import Decision, Verdict


@dataclass
class AutonomyPolicy:
    # Auto-clear only when BENIGN and confident enough.
    clear_confidence: float = 0.6
    # Any suspicion-weight at/above this always escalates, regardless of verdict.
    escalate_suspicion_floor: float = 0.7

    def decide(self, verdict: Verdict, confidence: float,
               suspicion_weight: float) -> tuple[Decision, str]:
        if suspicion_weight >= self.escalate_suspicion_floor:
            return (Decision.ESCALATE,
                    f"Escalated: total suspicion weight {suspicion_weight:.2f} ≥ floor "
                    f"{self.escalate_suspicion_floor}. Consequential — a human must decide.")
        if verdict == Verdict.BENIGN and confidence >= self.clear_confidence:
            return (Decision.AUTO_CLEAR,
                    f"Auto-cleared: verdict benign at confidence {confidence:.2f} ≥ "
                    f"{self.clear_confidence}. Logged with full rationale; no human needed.")
        return (Decision.ESCALATE,
                f"Escalated: verdict '{verdict.value}' at confidence {confidence:.2f} is "
                f"below the auto-clear bar — routed to the compliance officer.")
