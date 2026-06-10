"""Consortium Liaison (§5 #10, headline §7) — asks peer-bank meshes whether
they've seen the same ABSTRACT pattern. Only a pattern descriptor crosses the
boundary — never names, accounts, or transactions.
"""
from __future__ import annotations

from ..band.interface import CaseRoom
from ..band.stub import LocalMesh
from ..data.schema import Case, Verdict
from ..graph import EntityGraph
from .base import BaseAgent


class ConsortiumLiaisonAgent(BaseAgent):
    name = "consortium_liaison"
    tier = "specialist"

    def derive_pattern(self, case: Case) -> dict:
        """Reduce the case to an ABSTRACT descriptor — the ONLY thing shared."""
        eg = EntityGraph(case)
        hub = eg.detect_hub(case.focus_account)
        typology = case.alert_type
        if hub:
            typology = "fan-in-then-burst"
        return {  # note: zero PII, zero account ids, zero amounts
            "typology": typology,
            "txn_window_h": 72,
            "legs": len(case.transactions),
            "passthrough": bool(hub),
        }

    def query_peers(self, case: Case, mesh: LocalMesh, peers: list[str],
                    room: CaseRoom) -> str | None:
        pattern = self.derive_pattern(case)
        room.post(self.name, "consortium",
                  {"action": "query", "shared_payload": pattern,
                   "note": "ONLY this abstract pattern leaves the bank; records stay put."})
        hits = mesh.consortium_query(peers, pattern)
        if hits:
            peer = hits[0]["peer"]
            note = (f"Peer bank '{peer}' independently reports the same "
                    f"'{pattern['typology']}' pattern — cross-institution corroboration "
                    f"(no customer data exchanged).")
            room.post(self.name, "consortium", {"action": "match", "peer": peer, "note": note})
            return note
        room.post(self.name, "consortium", {"action": "no_match"})
        return None
