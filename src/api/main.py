"""FastAPI backend (§11 #14). Investigates USER-PROVIDED transaction data —
uploaded CSV/Excel/JSON/PDF — streaming every agent action live to the
dashboard, and scores AEGIS against the public IBM AML benchmark. There is no
canned-fixture path: every verdict is computed from data the caller supplied.

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
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..band.interface import AuditEvent
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


async def _cases_from_request(file: UploadFile, focus: str, limit: int):
    """Read + parse an uploaded transaction file into investigation cases,
    translating size/parse problems into clean HTTP errors."""
    from ..data.user_upload import cases_from_upload

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 25 MB). Export a smaller slice.")
    try:
        return await asyncio.to_thread(
            cases_from_upload, data, file.filename or "upload.csv", focus or None, limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _result_dict(case, result) -> dict:
    return {
        "account": case.focus_account,
        "alert_type": case.alert_type,
        "transactions": len(case.transactions),
        "result": json.loads(result.model_dump_json()),
    }


@app.post("/api/analyze")
async def analyze_upload(file: UploadFile = File(...), focus: str = "",
                         limit: int = 5) -> dict:
    """Bring-your-own-data: upload a transaction file (CSV / Excel / JSON /
    text-based PDF) and AEGIS investigates the highest-risk accounts in it (or
    the one named in `focus`). The file is parsed in memory only — never
    stored. No labels are involved; this is real inference on the caller's
    data. Accounts are investigated in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    cases = await _cases_from_request(file, focus, limit)

    def _one(case) -> dict:
        return _result_dict(case, Orchestrator().investigate(case))

    def _run() -> list[dict]:
        with ThreadPoolExecutor(max_workers=min(4, len(cases))) as pool:
            return list(pool.map(_one, cases))

    results = await asyncio.to_thread(_run)
    return {"filename": file.filename, "accounts_analyzed": len(results),
            "results": results}


@app.post("/api/analyze/stream")
async def analyze_upload_stream(file: UploadFile = File(...), focus: str = "",
                                limit: int = 5):
    """Same as /api/analyze but streams NDJSON so the dashboard can show the
    governed audit trail — every specialist claim, challenge, verification and
    rejection — live while the caller's own data is being investigated.

    Line kinds: `plan` (accounts selected), `event` (one agent action),
    `account_result` (one finished verdict), `done` (summary)."""
    cases = await _cases_from_request(file, focus, limit)
    filename = file.filename or "upload.csv"

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_event(ev: AuditEvent) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait, {"kind": "event", "payload": _event_dict(ev)})

    async def runner():
        # Sequential on purpose: the audit feed should read as one coherent
        # investigation at a time, not four interleaved ones.
        await queue.put({"kind": "plan", "payload": {
            "filename": filename,
            "accounts": [{"account": c.focus_account, "alert_type": c.alert_type,
                          "transactions": len(c.transactions)} for c in cases]}})
        results = []
        for case in cases:
            result = await asyncio.to_thread(
                Orchestrator().investigate, case, None, on_event)
            r = _result_dict(case, result)
            results.append(r)
            await queue.put({"kind": "account_result", "payload": r})
        await queue.put({"kind": "done", "payload": {
            "filename": filename, "accounts_analyzed": len(results)}})
        await queue.put({"kind": "__close__"})

    async def ndjson():
        task = asyncio.create_task(runner())
        while True:
            item = await queue.get()
            if item["kind"] == "__close__":
                break
            yield json.dumps(item) + "\n"
        await task

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


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
