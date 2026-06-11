"""AEGIS on Band — a real remote agent on the Band platform (by Nvoi).

Band (https://band.ai) is the shared-room collaboration layer where agents and
humans work together. This module connects AEGIS to it: a compliance officer in
a Band chatroom can say

    @AEGIS investigate the mule fixture with the consortium check

and this agent runs the full 10-agent AEGIS pipeline (specialists -> challenger
-> verifier -> consortium -> adjudicator) and posts the governed result — the
verdict, confidence, surviving cited evidence, and the audit-trail summary —
back into the room where everyone can see it.

Setup (see README / .env.example):
  1. pip install "band-sdk[langgraph]" langchain-openai
  2. Sign in at https://app.band.ai, create a *remote agent* (e.g. "AEGIS"),
     copy its UUID and API key into BAND_AGENT_ID / BAND_AGENT_KEY.
  3. python -m src.band.band_agent      (leave it running; chat in Band)

The agent's own LLM brain is an OpenAI-compatible ChatOpenAI pointed at the
AI/ML API reasoning tier (AIMLAPI_KEY), so the Band layer and the model layer
use the same providers as the rest of AEGIS. BAND_REST_URL / BAND_WS_URL
default to Band Cloud — override only for self-hosted Band.
"""
from __future__ import annotations

import asyncio
import json
import logging

from ..config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_investigation(fixture: str, consortium: bool) -> str:
    """Shared implementation behind the Band tools (plain function, testable)."""
    from . import LocalMesh
    from ..data.synthetic import DEMO_FIXTURES, get_fixture
    from ..orchestrator import Orchestrator

    if fixture not in DEMO_FIXTURES:
        return (f"Unknown fixture '{fixture}'. Available: "
                f"{', '.join(sorted(DEMO_FIXTURES))}")
    case = get_fixture(fixture)

    peers: list[str] = []
    if consortium:
        # Pre-seed a peer bank so the consortium demo finds a match (§7).
        peer = LocalMesh(tenant_id="bank-beta")
        peer.publish_pattern({"typology": "fan-in-then-burst", "txn_window_h": 72,
                              "legs": 5, "passthrough": True})
        peers = ["bank-beta"]

    events: list[str] = []
    orch = Orchestrator()
    orch.mesh.subscribe(lambda ev: events.append(f"{ev.actor}:{ev.kind}"))
    result = orch.investigate(case, peers)

    evidence = [{"agent": e.agent, "claim": e.claim, "source": e.source,
                 "confidence": e.confidence} for e in result.verified_evidence()]
    return json.dumps({
        "case_id": case.case_id,
        "alert_type": case.alert_type,
        "verdict": result.verdict.value,
        "confidence": result.confidence,
        "decision": result.decision.value,
        "rationale": result.rationale,
        "verified_evidence": evidence,
        "rejected_claims": result.rejected_claims,
        "consortium": result.consortium_confirmation,
        "audit_trail": {"events": len(events), "sequence": events},
    }, indent=2)


def build_adapter():
    """LangGraph adapter whose brain is the AEGIS reasoning tier (AI/ML API)."""
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver

    from band.adapters import LangGraphAdapter

    @tool
    def aegis_list_fixtures() -> str:
        """List the demo case fixtures AEGIS can investigate."""
        from ..data.synthetic import DEMO_FIXTURES
        return ", ".join(sorted(DEMO_FIXTURES))

    @tool
    def aegis_investigate(fixture: str, consortium: bool = False) -> str:
        """Run a full AEGIS multi-agent AML investigation on a demo fixture.

        Args:
            fixture: which case to investigate (use aegis_list_fixtures to see them)
            consortium: also query peer banks for matching abstract patterns
        """
        return _run_investigation(fixture, consortium)

    # Brain = the reasoning tier (AI/ML API); degrades to local Ollama if no
    # key, mirroring ModelClient's fallback rule so this never hard-crashes.
    cfg = settings.providers["aimlapi"]
    if not cfg.api_key:
        logger.warning("AIMLAPI_KEY not set — Band agent brain falling back to Ollama")
        cfg = settings.providers["ollama"]
    llm = ChatOpenAI(model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url)

    return LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        additional_tools=[aegis_list_fixtures, aegis_investigate],
        custom_section="""You are AEGIS, a multi-agent anti-money-laundering
investigation system. When someone in the room asks you to investigate a case:
  1. Call aegis_investigate (use aegis_list_fixtures if unsure of the name).
  2. Report the verdict, confidence and decision, then the surviving evidence
     as a short bullet list — ALWAYS include each claim's citation (its source
     field). Mention how many claims the Verifier rejected and why that matters
     (no evidence, no verdict). If a consortium confirmation is present, state
     that only an abstract pattern descriptor crossed banks, never raw data.
  3. Send the response with band_send_message.
Never invent evidence: only report what the tools return.""",
    )


async def main() -> None:
    from band import Agent

    agent_id = settings.band["agent_id"]
    api_key = settings.band["agent_key"]
    if not agent_id or not api_key:
        raise SystemExit(
            "BAND_AGENT_ID / BAND_AGENT_KEY are not set. Create a remote agent "
            "at https://app.band.ai and put its UUID + API key in .env.")

    agent = Agent.create(adapter=build_adapter(), agent_id=agent_id, api_key=api_key)
    logger.info("AEGIS Band agent starting — add it to a Band room and @mention it.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
