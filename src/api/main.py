"""FastAPI backend (§11 #14). Drives an investigation, streams every agent
action live to the dashboard via SSE, exposes the verdict/evidence and the
accuracy eval.

    uvicorn src.api.main:app --reload
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..band import LocalMesh
from ..band.interface import AuditEvent
from ..data.synthetic import DEMO_FIXTURES, get_fixture, labeled_dataset
from ..eval.harness import evaluate
from ..orchestrator import Orchestrator

app = FastAPI(title="AEGIS", version="0.2.0")
# In production the dashboard is served from this same origin (mount below), so
# no cross-origin access is needed at all. CORS exists only for local dev where
# the Next.js dev server runs on :3000; extend via CORS_ORIGINS if you host the
# UI elsewhere.
_cors_origins = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_methods=["*"],
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


@app.get("/api/eval/public")
async def run_eval_public(limit: int = 200) -> dict:
    """Baseline-vs-AEGIS on a bundled slice of a PUBLIC benchmark (IBM AML,
    HI-Small) with externally-authored labels — the credible number (§9). Falls
    back to a clear message if the sample isn't bundled."""
    from ..data.public_loader import bundled_sample_path, load_public

    path = bundled_sample_path("ibm")
    if not path:
        return {"error": "no bundled public benchmark sample available"}
    cases = await asyncio.to_thread(load_public, path, "generic", limit)
    return await asyncio.to_thread(evaluate, cases, "public:ibm-aml-sample")


_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB covers sizeable ledger exports


@app.post("/api/analyze")
async def analyze_upload(file: UploadFile = File(...), focus: str = "",
                         limit: int = 5) -> dict:
    """Bring-your-own-data: upload a transaction file (CSV / Excel / JSON /
    text-based PDF) and AEGIS investigates the most active accounts in it (or
    the one named in `focus`). The file is parsed in memory only — never
    stored. No labels are involved; this is real inference on the caller's
    data. Accounts are investigated in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    from ..data.user_upload import cases_from_upload

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 25 MB). Export a smaller slice.")
    try:
        cases = await asyncio.to_thread(
            cases_from_upload, data, file.filename or "upload.csv", focus or None, limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    def _one(case) -> dict:
        result = Orchestrator().investigate(case)
        return {
            "account": case.focus_account,
            "alert_type": case.alert_type,
            "transactions": len(case.transactions),
            "result": json.loads(result.model_dump_json()),
        }

    def _run() -> list[dict]:
        with ThreadPoolExecutor(max_workers=min(4, len(cases))) as pool:
            return list(pool.map(_one, cases))

    results = await asyncio.to_thread(_run)
    return {"filename": file.filename, "accounts_analyzed": len(results),
            "results": results}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ts": datetime.now(UTC).isoformat()}


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
