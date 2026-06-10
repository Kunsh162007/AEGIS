"""Framework adapters — the 'two frameworks on purpose' production path (§6, §19).

The core orchestrator runs WITHOUT these (USE_FRAMEWORKS=false) so the system is
always demoable. When USE_FRAMEWORKS=true:

  * the four specialists run as a CrewAI crew      -> crew_specialists.py
  * the Challenger/Verifier/Consortium/Adjudicator run as a real LangGraph
    StateGraph                                     -> langgraph_verification.py

The SAME agent methods (`investigate()` / `challenge()` / `verify()` /
`query_peers()` / `adjudicate()`) are reused unchanged — the adapters only move
who drives control flow into the framework. Each adapter exposes
`frameworks_available()` and degrades to the agnostic path if its library is
absent, so nothing is ever required to run AEGIS.

LangGraph runs with zero API keys (graph topology is pure Python; agents narrate
through the mock client). CrewAI's heavier stack may need keys/installation;
when unavailable the crew adapter runs the specialists directly and says so in
the audit stream.
"""
from . import crew_specialists, langgraph_verification

__all__ = ["crew_specialists", "langgraph_verification"]
