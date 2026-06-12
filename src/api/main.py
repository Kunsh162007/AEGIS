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

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..band.interface import AuditEvent
from ..casework import get_department
from ..config import settings
from ..eval.harness import evaluate

app = FastAPI(title="AEGIS", version="0.2.0")
# In production the dashboard is served from this same origin (mount below), so
# no cross-origin access is needed at all. CORS exists only for local dev where
# the Next.js dev server runs on :3000; extend via CORS_ORIGINS if you host the
# UI elsewhere.
_cors_origins = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_methods=["*"],
                   allow_headers=["*"])


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional production auth (§config.api_key): when AEGIS_API_KEY is set,
    every state-changing endpoint demands a matching X-API-Key header."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(401, "Missing or invalid X-API-Key.")


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


@app.post("/api/analyze", dependencies=[Depends(require_key)])
async def analyze_upload(file: UploadFile = File(...), focus: str = "",
                         limit: int = 5) -> dict:
    """Bring-your-own-data: upload a transaction file (CSV / Excel / JSON /
    text-based PDF) and AEGIS investigates the highest-risk accounts in it (or
    the one named in `focus`). The file is parsed in memory only — never
    stored. No labels are involved; this is real inference on the caller's
    data. Accounts are investigated in parallel, and every verdict is filed in
    the department casebook for the Command Center review queue."""
    from concurrent.futures import ThreadPoolExecutor

    cases = await _cases_from_request(file, focus, limit)
    filename = file.filename or "upload.csv"
    dept = get_department()

    def _one(case) -> dict:
        result = dept.orchestrator().investigate(case)
        row = dept.record_case(case, result, source_file=filename)
        d = _result_dict(case, result)
        d["case"] = {k: row[k] for k in ("uid", "priority", "sla_due", "status")}
        return d

    def _run() -> list[dict]:
        with ThreadPoolExecutor(max_workers=min(4, len(cases))) as pool:
            return list(pool.map(_one, cases))

    results = await asyncio.to_thread(_run)
    return {"filename": filename, "accounts_analyzed": len(results),
            "results": results}


@app.post("/api/analyze/stream", dependencies=[Depends(require_key)])
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
        dept = get_department()
        results = []
        for case in cases:
            result = await asyncio.to_thread(
                dept.orchestrator().investigate, case, None, on_event)
            row = await asyncio.to_thread(
                dept.record_case, case, result, filename)
            r = _result_dict(case, result)
            r["case"] = {k: row[k] for k in ("uid", "priority", "sla_due", "status")}
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


# ── The Command Center: case desk, operations, intelligence ─────────────────
# Everything below reads ONLY the department casebook, which is populated by
# real analyses (uploads / CLI) — there is no fixture path.

@app.get("/api/cases")
async def list_cases(status: str = "", limit: int = 100) -> dict:
    """The case queue, highest priority first. Filter with
    ?status=pending_review|auto_cleared|confirmed_suspicious|dismissed_false_positive."""
    dept = get_department()
    rows = await asyncio.to_thread(dept.store.list, status or None, limit)
    return {"cases": rows, "count": len(rows)}


@app.get("/api/cases/{uid}")
async def get_case(uid: str) -> dict:
    dept = get_department()
    row = await asyncio.to_thread(dept.store.get, uid)
    if row is None:
        raise HTTPException(404, f"No case {uid} in the casebook.")
    return row


class DecisionBody(BaseModel):
    decision: str  # "confirm" (suspicious) | "dismiss" (false positive)


@app.post("/api/cases/{uid}/decision", dependencies=[Depends(require_key)])
async def decide_case(uid: str, body: DecisionBody) -> dict:
    """The human compliance officer's gate. One decision does three things:
    closes the case, tunes the autonomy thresholds, and files the reviewed
    precedent into the knowledge base for future investigations."""
    dept = get_department()
    try:
        return await asyncio.to_thread(dept.decide, uid, body.decision)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/operations")
async def operations() -> dict:
    """Department KPIs — auto-clear rate, pending/overdue reviews, QA average,
    estimated analyst-hours saved (assumptions stated in the payload), and the
    current learned policy thresholds with recent feedback history."""
    return await asyncio.to_thread(get_department().operations)


@app.get("/api/intel/briefing")
async def intel_briefing() -> dict:
    """The Strategic Intelligence agent's cross-case briefing: emerging
    typologies, repeat subjects, counterparties bridging separate
    investigations, and consortium-ready abstract pattern descriptors."""
    from ..agents.strategic_intel import StrategicIntelAgent

    dept = get_department()
    rows = await asyncio.to_thread(dept.store.list, None, 500)
    return StrategicIntelAgent().brief(rows)


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
