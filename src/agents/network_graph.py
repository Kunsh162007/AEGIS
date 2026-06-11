"""Network / Graph specialist (§5 #4) — runs the real EntityGraph to find
mule hubs, cycles (round-tripping), and connected structures.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..data.schema import Case, Evidence, Verdict
from ..graph import EntityGraph
from .base import BaseAgent


class NetworkGraphAgent(BaseAgent):
    name = "network_graph"
    tier = "specialist"
    required_scope = "txn:read"

    def investigate(self, case: Case, room: CaseRoom) -> list[Evidence]:
        if not self._guarded(case, room):
            return []
        ev: list[Evidence] = []
        eg = EntityGraph(case)

        hub = eg.detect_hub(case.focus_account)
        if hub:
            ev.append(self._evidence(
                f"Focus account is a hub: {len(hub['feeders'])} feeders → "
                f"{len(hub['sinks'])} sink(s), pass-through ratio "
                f"{hub['pass_through_ratio']} — mule-network structure.",
                source=f"graph:hub({case.focus_account})", weight=0.8))

        cycles = eg.detect_cycles()
        if cycles:
            ev.append(self._evidence(
                f"{len(cycles)} cycle(s) in the money-flow graph (e.g. "
                f"{' → '.join(cycles[0])}) — round-tripping / layering.",
                source="graph:cycles", weight=0.75))

        # Being linked to several entities is true of any ordinary account (a
        # household pays many merchants) — weak context only, never enough to
        # cross the escalation floor without a hub/cycle alongside it.
        connected = eg.connected_entities(case.focus_account)
        if len(connected) >= 4:
            ev.append(self._evidence(
                f"Focus account is linked to {len(connected)} other entities in one "
                f"connected component — broad network exposure.",
                source=f"graph:component({case.focus_account})", weight=0.25))

        if not ev:
            ev.append(self._evidence(
                "No mule hub, cycle, or dense linkage around the focus account.",
                source="graph:scan", weight=0.2, supports=Verdict.BENIGN))

        for e in ev:
            room.post(self.name, "evidence", e.model_dump(mode="json"))
        return ev
