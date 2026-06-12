"""AEGIS on Band — a real remote agent on the Band platform (by Nvoi).

Band (https://band.ai) is the shared-room collaboration layer where agents and
humans work together. This module connects AEGIS to it: a compliance officer in
a Band chatroom can paste transaction rows (CSV) and say

    @AEGIS investigate these transactions

and this agent runs the full 10-agent AEGIS pipeline (specialists -> challenger
-> verifier -> consortium -> adjudicator) on that real data and posts the
governed result — the verdict, confidence, surviving cited evidence, and the
audit-trail summary — back into the room where everyone can see it.

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


def _run_investigation(transactions_csv: str, focus: str = "") -> str:
    """Shared implementation behind the Band tool (plain function, testable).
    Takes REAL transaction rows pasted into the room — never canned cases."""
    from ..data.user_upload import cases_from_upload
    from ..orchestrator import Orchestrator

    try:
        cases = cases_from_upload(transactions_csv.encode("utf-8"),
                                  "band-room.csv", focus.strip() or None, limit=3)
    except ValueError as exc:
        return (f"Could not parse the transaction data: {exc} "
                f"Paste CSV rows with headers like from,to,amount(,date,type).")

    reports = []
    for case in cases:
        events: list[str] = []
        orch = Orchestrator()
        orch.mesh.subscribe(lambda ev: events.append(f"{ev.actor}:{ev.kind}"))
        result = orch.investigate(case)
        evidence = [{"agent": e.agent, "claim": e.claim, "source": e.source,
                     "confidence": e.confidence} for e in result.verified_evidence()]
        reports.append({
            "account": case.focus_account,
            "alert_type": case.alert_type,
            "transactions_reviewed": len(case.transactions),
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "decision": result.decision.value,
            "rationale": result.rationale,
            "verified_evidence": evidence,
            "rejected_claims": result.rejected_claims,
            "consortium": result.consortium_confirmation,
            "audit_trail": {"events": len(events), "sequence": events},
        })
    return json.dumps({"accounts_analyzed": len(reports), "results": reports},
                      indent=2)


def build_adapter():
    """LangGraph adapter whose brain is the AEGIS reasoning tier (AI/ML API)."""
    import os

    # AI/ML API streams can stall >120s mid-response (free-tier throttling),
    # which trips langchain-openai's default chunk timeout and fails the whole
    # Band message. Give it 300s unless the user tuned it themselves.
    os.environ.setdefault("LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S", "300")

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver

    from band.adapters import LangGraphAdapter

    @tool
    def aegis_investigate(transactions_csv: str, focus: str = "") -> str:
        """Run a full AEGIS multi-agent AML investigation on real transaction data.

        Args:
            transactions_csv: the transaction rows as CSV text, including a header
                row with columns for source account, destination account and
                amount (e.g. from,to,amount,date,type). Pass the data exactly as
                the user shared it.
            focus: optionally a single account id to investigate; otherwise the
                highest-risk accounts are triaged automatically.
        """
        return _run_investigation(transactions_csv, focus)

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
        additional_tools=[aegis_investigate],
        custom_section="""You are AEGIS, a multi-agent anti-money-laundering
investigation system. You only ever analyze REAL transaction data shared in
the room — if someone asks you to investigate without providing data, ask them
to paste their transaction rows (CSV with source, destination and amount
columns) or upload them to the AEGIS dashboard. When data is provided:
  1. Call aegis_investigate with the rows exactly as shared (and `focus` if
     they named one account).
  2. For each account report the verdict, confidence and decision, then the
     surviving evidence as a short bullet list — ALWAYS include each claim's
     citation (its source field). Mention how many claims the Verifier rejected
     and why that matters (no evidence, no verdict). If a consortium
     confirmation is present, state that only an abstract pattern descriptor
     crossed banks, never raw data.
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
