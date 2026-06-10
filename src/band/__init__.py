"""Band transport layer. Agent logic is decoupled from Band so the mesh can be
finished independently and a Band hiccup never takes the system down (§4).

`interface.BandMesh` is the abstract contract; `stub.LocalMesh` implements it
in-process. Once the official Band SDK is available, add `real.BandMesh` mapping
these same behaviours to it — DO NOT invent method names before then (§6).
"""
from .interface import AuditEvent, BandMesh, CaseRoom
from .stub import LocalMesh

__all__ = ["BandMesh", "CaseRoom", "AuditEvent", "LocalMesh", "get_mesh"]


def get_mesh(tenant_id: str = "bank-alpha") -> BandMesh:
    """Factory. Swap to the real Band mesh here once the SDK is wired."""
    return LocalMesh(tenant_id=tenant_id)
