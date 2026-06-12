"""FastAPI backend (§11 #14). Investigates USER-PROVIDED transaction data —
uploaded CSV/Excel/JSON/PDF — streaming every agent action live to the
dashboard, and scores AEGIS against the public IBM AML benchmark. There is no
canned-fixture path: every verdict is computed from data the caller supplied.

    uvicorn src.api.main:app --reload
"""
from __future__ import annotations

import asyncio
import json
import re
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
from ..data.schema import Verdict

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


def _flagged_transactions(case, result) -> dict[str, list[str]]:
    """Map txn_id -> reasons, parsed from the VERIFIED suspicious evidence's
    citations — this is how the suspicious areas of the user's own dataset get
    marked row by row. Bracketed ids cite transactions directly; account
    citations like txn:inbound(ACC) flag the transactions touching that
    account."""
    txn_ids = {t.txn_id for t in case.transactions}
    flags: dict[str, list[str]] = {}

    def _mark(tid: str, reason: str) -> None:
        flags.setdefault(tid, [])
        if reason not in flags[tid]:
            flags[tid].append(reason)

    for e in result.verified_evidence():
        if e.supports != Verdict.SUSPICIOUS:
            continue
        reason = f"{e.agent}: {e.claim}"
        cited = False
        for chunk in re.findall(r"\[([^\]]+)\]", e.source):
            for part in chunk.split(","):
                tid = part.strip()
                if tid in txn_ids:
                    _mark(tid, reason)
                    cited = True
        if cited or not e.source.startswith(("txn:", "graph:")):
            continue
        # Account-level citation: flag the focus account's flows with that
        # party — respecting the claim's direction so an outbound transfer is
        # never explained by an "inbound velocity" reason.
        semantics = e.source.split("(", 1)[0]
        for acct in re.findall(r"\(([^)]+)\)", e.source):
            for t in case.transactions:
                if acct not in (t.src_account, t.dst_account) or \
                        case.focus_account not in (t.src_account, t.dst_account):
                    continue
                if semantics.endswith("inbound") and t.dst_account != acct:
                    continue
                if semantics.endswith("outbound") and t.src_account != acct:
                    continue
                _mark(t.txn_id, reason)
    return flags


def _result_dict(case, result) -> dict:
    return {
        "account": case.focus_account,
        "alert_type": case.alert_type,
        "transactions": len(case.transactions),
        "result": json.loads(result.model_dump_json()),
        # The case's transaction rows + which of them are flagged and why —
        # lets the UI mark the suspicious areas of the uploaded dataset itself.
        "txns": [{"txn_id": t.txn_id, "src": t.src_account, "dst": t.dst_account,
                  "amount": t.amount, "ts": t.timestamp.isoformat(),
                  "channel": t.channel} for t in case.transactions],
        "flagged_txns": _flagged_transactions(case, result),
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
    investigations, consortium-ready abstract descriptors — and any
    potentially NOVEL patterns (suspicious structure matching no library
    typology)."""
    from ..agents.strategic_intel import StrategicIntelAgent
    from ..casework.patterns import looks_novel

    dept = get_department()
    rows = await asyncio.to_thread(dept.store.list, None, 500)
    briefing = StrategicIntelAgent().brief(rows)

    flagged = {r["uid"]: r for r in rows if r["verdict"] in ("suspicious", "uncertain")}
    briefing["novel_patterns"] = [
        {"case_uid": p["case_uid"], "account": p["account"],
         "signature": p["signature"], "outcome": p["outcome"]}
        for p in await asyncio.to_thread(dept.store.list_patterns)
        if p["case_uid"] in flagged and looks_novel(p["signature"])]
    return briefing


# ── The chat analyst: grounded Q&A over the org's data and cases ─────────────

class ChatBody(BaseModel):
    question: str


@app.post("/api/chat", dependencies=[Depends(require_key)])
async def chat(body: ChatBody) -> dict:
    """Ask AEGIS about the data: verdicts, why an account was flagged, what a
    typology means, what's pending. Facts are computed from the casebook; the
    LLM (live mode) only rephrases them — it never invents numbers."""
    from ..agents.chat_analyst import ChatAnalystAgent

    q = body.question.strip()
    if not q:
        raise HTTPException(422, "Empty question.")
    agent = ChatAnalystAgent(store=get_department().store)
    return await asyncio.to_thread(agent.answer, q[:500])


@app.get("/api/typologies")
async def typologies() -> dict:
    """The fraud-typology library — used by the UI to explain each type of
    fraud discovered in an analysis."""
    from ..knowledge.typologies import TYPOLOGIES
    return {"typologies": TYPOLOGIES}


# ── Org personalisation: the company's own rules + historical baselines ─────

class OrgProfileBody(BaseModel):
    name: str = ""
    ctr_threshold: float = 10_000.0
    watchlist: list[str] | str = []
    trusted_counterparties: list[str] | str = []
    policy_notes: list[str] | str = []


@app.get("/api/org/profile")
async def get_org_profile() -> dict:
    dept = get_department()
    profile = await asyncio.to_thread(dept.store.get_org_profile)
    baselines = await asyncio.to_thread(dept.store.baseline_count)
    return {"profile": profile, "baseline_accounts": baselines}


@app.post("/api/org/profile", dependencies=[Depends(require_key)])
async def set_org_profile(body: OrgProfileBody) -> dict:
    """Register the organisation's own compliance context: watchlist, trusted
    counterparties, internal reporting threshold, policy notes. Every
    subsequent investigation applies it via the Org Policy agent."""
    from ..casework.org import normalize_profile

    profile = normalize_profile(body.model_dump())
    dept = get_department()
    await asyncio.to_thread(dept.store.save_org_profile, profile)
    return {"profile": profile, "saved": True}


@app.post("/api/org/history", dependencies=[Depends(require_key)])
async def upload_org_history(file: UploadFile = File(...)) -> dict:
    """Upload the org's PREVIOUS transaction data (CSV/Excel/JSON/PDF). AEGIS
    builds per-account behavioural baselines from it, so 'unusual' is measured
    against each account's own history. Parsed in memory; only the aggregate
    baselines are stored."""
    from ..casework.org import baselines_from_edges
    from ..data.user_upload import parse_upload

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 25 MB).")
    try:
        edges = await asyncio.to_thread(parse_upload, data,
                                        file.filename or "history.csv")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    rows = baselines_from_edges(edges)
    dept = get_department()
    n = await asyncio.to_thread(dept.store.save_baselines, rows)
    return {"filename": file.filename, "baseline_accounts": n,
            "transactions_processed": len(edges)}


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
