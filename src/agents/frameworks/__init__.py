"""Framework adapters — the 'two frameworks on purpose' production path (§6, §19).

The core orchestrator runs WITHOUT these (USE_FRAMEWORKS=false) so the system is
always demoable. When USE_FRAMEWORKS=true, wrap the SAME agent logic so that:

  * the four CrewAI specialists run as a CrewAI Crew, and
  * the Challenger/Verifier/Adjudicator run as a LangGraph StateGraph,

both joining the Band room. The agents' `investigate()` / `challenge()` /
`verify()` / `adjudicate()` methods are framework-agnostic on purpose — these
adapters only wire them into CrewAI Tasks and LangGraph nodes; no logic moves.

Left as scaffolding because CrewAI + LangGraph add heavy deps and must be wired
against live model keys. Fill in once Featherless/AI-ML keys are set:

    from crewai import Agent as CrewAgent, Task, Crew
    from langgraph.graph import StateGraph

See README "Production framework path" for the step-by-step.
"""

USE_FRAMEWORKS_DOC = __doc__
