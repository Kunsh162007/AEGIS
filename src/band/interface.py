"""Abstract Band contract — the behaviours from the proposal (§4, §6), not the
real method names. The real SDK is mapped onto this contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class AuditEvent:
    """One governed who-did-what-on-whose-authority record (§4)."""
    ts: datetime
    room_id: str
    actor: str                 # agent or human id
    kind: str                  # joined | evidence | challenge | verdict | gate | consortium | clear
    authority: str             # whose credentials this action ran under
    payload: dict = field(default_factory=dict)


@dataclass
class Credential:
    """The human case officer's permissions, propagated across agents (§4)."""
    officer_id: str
    scopes: set[str] = field(default_factory=set)   # e.g. {"txn:read", "kyc:read"}

    def allows(self, scope: str) -> bool:
        return scope in self.scopes or "*" in self.scopes


class CaseRoom(ABC):
    room_id: str
    credential: Credential

    @abstractmethod
    def post(self, actor: str, kind: str, payload: dict) -> None: ...

    @abstractmethod
    def recruit(self, role: str) -> None: ...

    @abstractmethod
    def require_scope(self, actor: str, scope: str) -> bool:
        """Credential traversal check — actor may only touch what the officer can."""

    @abstractmethod
    def request_human_gate(self, summary: dict) -> None: ...

    @abstractmethod
    def history(self) -> list[AuditEvent]: ...


class BandMesh(ABC):
    tenant_id: str

    @abstractmethod
    def open_room(self, case_id: str, credential: Credential) -> CaseRoom: ...

    @abstractmethod
    def subscribe(self, handler: Callable[[AuditEvent], Any]) -> None:
        """Stream every audit event live (drives the dashboard SSE)."""

    @abstractmethod
    def consortium_query(self, peer_tenants: list[str], pattern: dict) -> list[dict]:
        """Ask peer-bank meshes about an ABSTRACT pattern. No raw records (§7)."""
