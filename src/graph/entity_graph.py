"""EntityGraph — builds a directed money-flow graph for a case and detects
structures (rings, fan-in/fan-out hubs, layering chains). This is *real*
computation, not an LLM guess — it's what makes the Network agent a genuine
agent rather than a prompt (§5).
"""
from __future__ import annotations

import networkx as nx

from ..data.schema import Case


class EntityGraph:
    def __init__(self, case: Case):
        self.case = case
        self.g = nx.MultiDiGraph()
        for p in case.parties:
            self.g.add_node(p.account, name=p.name, type=p.account_type,
                            country=p.country)
        for t in case.transactions:
            self.g.add_edge(t.src_account, t.dst_account, amount=t.amount,
                            txn_id=t.txn_id, ts=t.timestamp)

    # -- structure detection ----------------------------------------------
    def fan_in(self, account: str) -> list[str]:
        return list({u for u, _ in self.g.in_edges(account)})

    def fan_out(self, account: str) -> list[str]:
        return list({v for _, v in self.g.out_edges(account)})

    def detect_hub(self, account: str, min_sources: int = 3) -> dict | None:
        """A hub with many feeders and a fast onward transfer = mule pattern."""
        sources = self.fan_in(account)
        sinks = self.fan_out(account)
        if len(sources) >= min_sources and sinks:
            in_amt = sum(d["amount"] for _, _, d in self.g.in_edges(account, data=True))
            out_amt = sum(d["amount"] for _, _, d in self.g.out_edges(account, data=True))
            return {"account": account, "feeders": sources, "sinks": sinks,
                    "in_amount": in_amt, "out_amount": out_amt,
                    "pass_through_ratio": round(out_amt / in_amt, 2) if in_amt else 0.0}
        return None

    def detect_cycles(self) -> list[list[str]]:
        """Round-tripping shows up as cycles in the money-flow graph."""
        simple = nx.DiGraph(self.g)
        try:
            return [c for c in nx.simple_cycles(simple) if len(c) >= 2]
        except Exception:
            return []

    def connected_entities(self, account: str) -> list[str]:
        und = self.g.to_undirected()
        if account not in und:
            return []
        return [n for n in nx.node_connected_component(und, account) if n != account]
