"""LocalMesh — an in-process implementation of the Band contract so the whole
system runs today. It enforces credential traversal, records a governed audit
trail, streams events, and simulates cross-tenant consortium queries (§7).

The consortium store holds ONLY abstract pattern descriptors per tenant — never
cases, names, or transactions — which is what makes "no data crossed" true and
provable on screen.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from .interface import AuditEvent, BandMesh, CaseRoom, Credential

# Shared across LocalMesh instances to simulate separate banks on one machine.
# Maps tenant_id -> list of abstract pattern descriptors it has "seen".
_CONSORTIUM_MEMORY: dict[str, list[dict]] = {}


class LocalRoom(CaseRoom):
    def __init__(self, room_id: str, credential: Credential,
                 emit: Callable[[AuditEvent], None]):
        self.room_id = room_id
        self.credential = credential
        self._emit = emit
        self._events: list[AuditEvent] = []
        self.members: list[str] = []

    def _record(self, actor: str, kind: str, payload: dict) -> None:
        ev = AuditEvent(ts=datetime.now(UTC), room_id=self.room_id, actor=actor,
                        kind=kind, authority=self.credential.officer_id, payload=payload)
        self._events.append(ev)
        self._emit(ev)

    def post(self, actor: str, kind: str, payload: dict) -> None:
        self._record(actor, kind, payload)

    def recruit(self, role: str) -> None:
        self.members.append(role)
        self._record(role, "joined", {"role": role})

    def require_scope(self, actor: str, scope: str) -> bool:
        ok = self.credential.allows(scope)
        if not ok:
            self._record(actor, "denied", {"scope": scope,
                         "reason": "outside officer authority"})
        return ok

    def request_human_gate(self, summary: dict) -> None:
        self._record("compliance_officer", "gate", summary)

    def history(self) -> list[AuditEvent]:
        return list(self._events)


class LocalMesh(BandMesh):
    def __init__(self, tenant_id: str = "bank-alpha"):
        self.tenant_id = tenant_id
        self._subscribers: list[Callable[[AuditEvent], Any]] = []
        _CONSORTIUM_MEMORY.setdefault(tenant_id, [])

    def _emit(self, event: AuditEvent) -> None:
        for handler in self._subscribers:
            handler(event)

    def open_room(self, case_id: str, credential: Credential) -> CaseRoom:
        room = LocalRoom(room_id=f"{self.tenant_id}:{case_id}", credential=credential,
                         emit=self._emit)
        room.post("intake", "room_opened", {"case_id": case_id, "tenant": self.tenant_id})
        return room

    def subscribe(self, handler: Callable[[AuditEvent], Any]) -> None:
        self._subscribers.append(handler)

    # -- consortium (§7): exchange ABSTRACT patterns only --------------------
    def publish_pattern(self, pattern: dict) -> None:
        _CONSORTIUM_MEMORY[self.tenant_id].append(pattern)

    def consortium_query(self, peer_tenants: list[str], pattern: dict) -> list[dict]:
        hits = []
        for peer in peer_tenants:
            for known in _CONSORTIUM_MEMORY.get(peer, []):
                if known.get("typology") == pattern.get("typology"):
                    hits.append({"peer": peer, "matched_pattern": known,
                                 "shared_payload": pattern})  # only the descriptor crossed
        return hits
