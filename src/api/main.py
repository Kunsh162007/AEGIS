"""FastAPI backend (§11 #14). Drives an investigation, streams every agent
action live to the dashboard via SSE, exposes the verdict/evidence and the
accuracy eval.

    uvicorn src.api.main:app --reload
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..band import LocalMesh
from ..band.interface import AuditEvent, Credential
from ..data.synthetic import DEMO_FIXTURES, get_fixture
from ..eval.harness import evaluate
from ..data.synthetic import labeled_dataset
from ..orchestrator import Orchestrator

app = FastAPI(title="AEGIS", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def _event_dict(ev: AuditEvent) -> dict:
    return {"ts": ev.ts.isoformat(), "room": ev.room_id, "actor": ev.actor,
            "kind": ev.kind, "authority": ev.authority, "payload": ev.payload}


@app.get("/api/fixtures")
def fixtures() -> dict:
    return {"fixtures": list(DEMO_FIXTURES.keys())}


@app.get("/api/investigate/stream")
async def investigate_stream(fixture: str = "structuring", consortium: bool = False):
    """Run an investigation and stream each agent action as it happens."""
    case = get_fixture(fixture)
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_event(ev: AuditEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, _event_dict(ev))

    async def runner():
        # Pre-seed a peer bank so the consortium demo finds a match (§7).
        peers = []
        if consortium:
            peer = LocalMesh(tenant_id="bank-beta")
            peer.publish_pattern({"typology": "fan-in-then-burst", "txn_window_h": 72,
                                  "legs": 5, "passthrough": True})
            peers = ["bank-beta"]
        orch = Orchestrator()
        result = await asyncio.to_thread(orch.investigate, case, peers, on_event)
        await queue.put({"kind": "result", "payload": json.loads(result.model_dump_json())})
        await queue.put({"kind": "__done__"})

    async def event_source():
        task = asyncio.create_task(runner())
        while True:
            item = await queue.get()
            if item.get("kind") == "__done__":
                break
            yield {"data": json.dumps(item)}
        await task

    return EventSourceResponse(event_source())


@app.get("/api/investigate")
async def investigate(fixture: str = "structuring", consortium: bool = False) -> dict:
    case = get_fixture(fixture)
    peers = []
    if consortium:
        peer = LocalMesh(tenant_id="bank-beta")
        peer.publish_pattern({"typology": "fan-in-then-burst", "txn_window_h": 72,
                              "legs": 5, "passthrough": True})
        peers = ["bank-beta"]
    orch = Orchestrator()
    result = orch.investigate(case, peers)
    return json.loads(result.model_dump_json())


@app.get("/api/eval")
async def run_eval(limit: int = 40) -> dict:
    cases = labeled_dataset(n=limit)
    return await asyncio.to_thread(evaluate, cases, "synthetic")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}


# ── Serve the built dashboard (single-origin production deploy) ──────────────
# When `dashboard/out` exists (produced by `STATIC_EXPORT=1 npm run build`), serve
# the UI from FastAPI itself so the whole app is one service on one URL. Mounted
# LAST so it acts as a fallback — the /api/* routes above always match first.
# In local dev this directory is absent, so the API runs API-only and the
# Next.js dev server handles the UI.
_DASHBOARD_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "out"
if _DASHBOARD_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DASHBOARD_DIST), html=True),
              name="dashboard")
