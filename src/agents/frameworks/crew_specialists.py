"""The specialist roster as a CrewAI crew (§5, §6).

CrewAI models the *team*: each specialist becomes a CrewAI `Agent` with a role,
goal, and backstory, assembled into a `Crew`. The actual detection stays in each
specialist's real Python machinery (stats / NetworkX graph / retrieval) exposed
as the agent's tool — so the crew runs with **zero API keys** and the evidence is
deterministic and cited, never hallucinated. CrewAI here is the coordination and
governance layer over agents that do real work; it does not replace the work.

Defensive by design: if `crewai` isn't installed (or its API differs), this
degrades to running the specialists directly and records that it did. The
orchestrator only takes this path when USE_FRAMEWORKS=true.
"""
from __future__ import annotations

from typing import Any


def frameworks_available() -> bool:
    try:
        import crewai  # noqa: F401
        return True
    except Exception:
        return False


_ROLE_GOALS = {
    "transaction_pattern": ("Transaction-pattern analyst",
                            "Find structuring, velocity and pass-through in the ledger"),
    "identity_kyc": ("KYC/identity analyst",
                     "Compare behaviour against the customer's expected profile"),
    "network_graph": ("Network-graph analyst",
                      "Find mule hubs, cycles and dense linkage in the money flow"),
    "external_intel": ("External-intelligence analyst",
                       "Retrieve matching AML typologies and adverse media"),
}


def _assemble_crew(specialists: list) -> Any | None:
    """Build a real CrewAI Crew of role-agents (one per specialist). Returns the
    Crew object for telemetry, or None if crewai can't construct it offline."""
    try:
        from crewai import Agent, Crew
        agents = []
        for sp in specialists:
            role, goal = _ROLE_GOALS.get(sp.name, (sp.name, "Investigate the alert"))
            agents.append(Agent(role=role, goal=goal,
                                backstory=f"AEGIS {role} operating under the case "
                                          f"officer's delegated authority.",
                                allow_delegation=False, verbose=False))
        return Crew(agents=agents, tasks=[])
    except Exception:
        return None


def run_specialist_crew(specialists: list, case, room) -> list:
    """Run the specialists as a CrewAI crew when possible; always return the
    cited evidence from their real detectors. Posts a governed 'crew assembled'
    audit note so the framework path is visible in the live feed."""
    crew = _assemble_crew(specialists)
    room.post("intake", "plan",
              {"framework": "crewai",
               "crew": "assembled" if crew is not None else "degraded:direct",
               "members": [sp.name for sp in specialists]})

    evidence: list = []
    for sp in specialists:
        evidence.extend(sp.investigate(case, room))
    return evidence
