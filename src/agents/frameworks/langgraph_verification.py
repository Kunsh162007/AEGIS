"""The verification + decision trio as a REAL LangGraph StateGraph (§5, §6).

This is the production path for AEGIS's adversarial core: Challenger → Verifier →
Consortium → Adjudicator run as nodes of a compiled `langgraph` graph over a
shared state. No agent logic moves here — each node calls the SAME
`challenge()` / `verify()` / `query_peers()` / `adjudicate()` methods the
framework-agnostic orchestrator uses. The only thing that changes is *who drives
the control flow* (LangGraph vs. a plain Python sequence).

It runs with zero API keys: the graph topology is pure Python; the agents narrate
through the mock model client like everywhere else. If `langgraph` isn't
installed, `frameworks_available()` returns False and the orchestrator stays on
the agnostic path — the system is always runnable.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


def frameworks_available() -> bool:
    """True iff langgraph is importable (the orchestrator checks this before use)."""
    try:
        import langgraph  # noqa: F401
        from langgraph.graph import StateGraph  # noqa: F401
        return True
    except Exception:
        return False


class VerificationState(TypedDict, total=False):
    evidence: list
    challenge: dict
    rejected: list
    consortium_note: Optional[str]
    result: Any


def run_verification_graph(*, challenger, verifier, liaison, adjudicator,
                           case, evidence, room, mesh, peers) -> Any:
    """Build, compile, and invoke the LangGraph verification graph; return the
    CaseResult. Mirrors the orchestrator's verify→consortium→adjudicate stage."""
    from langgraph.graph import END, StateGraph

    def challenger_node(state: VerificationState) -> dict:
        return {"challenge": challenger.challenge(case, state["evidence"], room)}

    def verifier_node(state: VerificationState) -> dict:
        ev, rejected = verifier.verify(case, state["evidence"], state["challenge"], room)
        return {"evidence": ev, "rejected": rejected}

    def consortium_node(state: VerificationState) -> dict:
        note = liaison.query_peers(case, mesh, peers, room) if peers else None
        return {"consortium_note": note}

    def adjudicator_node(state: VerificationState) -> dict:
        result = adjudicator.adjudicate(
            case, state["evidence"], state["challenge"], state["rejected"], room,
            consortium_note=state.get("consortium_note"))
        return {"result": result}

    graph = StateGraph(VerificationState)
    graph.add_node("challenger", challenger_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("consortium", consortium_node)
    graph.add_node("adjudicator", adjudicator_node)
    graph.set_entry_point("challenger")
    graph.add_edge("challenger", "verifier")
    graph.add_edge("verifier", "consortium")
    graph.add_edge("consortium", "adjudicator")
    graph.add_edge("adjudicator", END)

    compiled = graph.compile()
    out = compiled.invoke({"evidence": evidence})
    return out["result"]
