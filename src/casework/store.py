"""CaseStore — the department's persistent casebook (SQLite, stdlib only).

Every investigation AEGIS runs over user data becomes a durable case with a
lifecycle, a priority, an SLA clock, and eventually the officer's decision:

    auto_cleared | pending_review -> confirmed_suspicious | dismissed_false_positive

It also persists what must survive a restart for the learning loop to be real:
officer feedback history, reviewed precedent for the knowledge base, and the
current tuned policy thresholds. Populated only by real analyses (uploads or
the CLI) — never by fixtures.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ..data.schema import Case, CaseResult, Decision
from .priority import exposure, priority_score, sla_due

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  uid TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  source_file TEXT,
  account TEXT,
  alert_type TEXT,
  txn_count INTEGER,
  exposure REAL,
  verdict TEXT,
  confidence REAL,
  decision TEXT,
  status TEXT,
  priority REAL,
  sla_due TEXT,
  qa_score REAL,
  counterparties TEXT,
  result_json TEXT,
  officer_decision TEXT,
  decided_at TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, case_uid TEXT, officer_decision TEXT, agreed INTEGER,
  clear_confidence_before REAL, clear_confidence_after REAL
);
CREATE TABLE IF NOT EXISTS precedents (
  doc_id TEXT PRIMARY KEY, text TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS baselines (
  account TEXT PRIMARY KEY, monthly_in REAL, monthly_out REAL,
  txn_count INTEGER, top_counterparties TEXT, channels TEXT, updated TEXT
);
CREATE TABLE IF NOT EXISTS patterns (
  case_uid TEXT PRIMARY KEY, account TEXT, signature TEXT,
  verdict TEXT, outcome TEXT, ts TEXT
);
"""

_MAX_COUNTERPARTIES = 25


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CaseStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # One shared connection guarded by a lock: investigations run in a
        # thread pool, and ":memory:" databases exist per-connection.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    # ── cases ────────────────────────────────────────────────────────────────
    def add_case(self, case: Case, result: CaseResult, source_file: str = "") -> dict:
        prio = priority_score(case, result)
        status = ("pending_review" if result.decision == Decision.ESCALATE
                  else "auto_cleared")
        counterparties = sorted({
            (t.dst_account if t.src_account == case.focus_account else t.src_account)
            for t in case.transactions
            if case.focus_account in (t.src_account, t.dst_account)
        } - {case.focus_account})[:_MAX_COUNTERPARTIES]
        row = {
            "uid": f"{case.case_id}-{uuid.uuid4().hex[:6]}",
            "created_at": _now(),
            "source_file": source_file,
            "account": case.focus_account,
            "alert_type": case.alert_type,
            "txn_count": len(case.transactions),
            "exposure": round(exposure(case), 2),
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "decision": result.decision.value,
            "status": status,
            "priority": prio,
            "sla_due": sla_due(prio).isoformat() if status == "pending_review" else None,
            "qa_score": result.qa_score,
            "counterparties": json.dumps(counterparties),
            "result_json": result.model_dump_json(),
            "officer_decision": None,
            "decided_at": None,
        }
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT INTO cases ({','.join(row)}) "
                f"VALUES ({','.join('?' * len(row))})", tuple(row.values()))
        return self._public(row)

    def get(self, uid: str) -> dict | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM cases WHERE uid=?", (uid,)).fetchone()
        return self._public(dict(r), full=True) if r else None

    def list(self, status: str | None = None, limit: int = 100) -> list[dict]:
        q = "SELECT * FROM cases"
        args: tuple = ()
        if status:
            q += " WHERE status=?"
            args = (status,)
        q += " ORDER BY priority DESC, created_at DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(q, args + (limit,)).fetchall()
        return [self._public(dict(r)) for r in rows]

    def set_decision(self, uid: str, officer_decision: str, status: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE cases SET officer_decision=?, status=?, decided_at=? WHERE uid=?",
                (officer_decision, status, _now(), uid))

    def counts_by_status(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) n FROM cases GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def overdue_reviews(self) -> int:
        with self._lock:
            r = self._conn.execute(
                "SELECT COUNT(*) n FROM cases WHERE status='pending_review' AND sla_due<?",
                (_now(),)).fetchone()
        return r["n"]

    def avg_qa_score(self) -> float | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT AVG(qa_score) a FROM cases WHERE qa_score IS NOT NULL").fetchone()
        return round(r["a"], 3) if r["a"] is not None else None

    # ── learning-loop persistence ────────────────────────────────────────────
    def add_feedback(self, entry: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO feedback (ts, case_uid, officer_decision, agreed,"
                " clear_confidence_before, clear_confidence_after)"
                " VALUES (?,?,?,?,?,?)",
                (_now(), entry["case_uid"], entry["officer_decision"],
                 int(entry["agreed"]), entry["clear_confidence_before"],
                 entry["clear_confidence_after"]))

    def feedback_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{k: r[k] for k in r.keys() if k != "id"} | {"agreed": bool(r["agreed"])}
                for r in rows]

    def add_precedent(self, doc_id: str, text: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO precedents (doc_id, text, ts) VALUES (?,?,?)",
                (doc_id, text, _now()))

    def precedents(self) -> list[tuple[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc_id, text FROM precedents ORDER BY ts").fetchall()
        return [(r["doc_id"], r["text"]) for r in rows]

    # ── org personalisation: profile + behavioural baselines ────────────────
    def save_org_profile(self, profile: dict) -> None:
        self.kv_set("org_profile", json.dumps(profile))

    def get_org_profile(self) -> dict | None:
        raw = self.kv_get("org_profile")
        return json.loads(raw) if raw else None

    def save_baselines(self, rows: list[dict]) -> int:
        with self._lock, self._conn:
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO baselines (account, monthly_in,"
                    " monthly_out, txn_count, top_counterparties, channels, updated)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (r["account"], r["monthly_in"], r["monthly_out"], r["txn_count"],
                     json.dumps(r["top_counterparties"]), json.dumps(r["channels"]),
                     _now()))
        return len(rows)

    def get_baseline(self, account: str) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM baselines WHERE account=?", (account,)).fetchone()
        if not r:
            return None
        out = dict(r)
        out["top_counterparties"] = json.loads(out["top_counterparties"] or "[]")
        out["channels"] = json.loads(out["channels"] or "[]")
        return out

    def baseline_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) n FROM baselines").fetchone()["n"]

    # ── pattern memory: the system improves with each analysis ─────────────
    def add_pattern(self, case_uid: str, account: str, signature: dict,
                    verdict: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO patterns (case_uid, account, signature,"
                " verdict, outcome, ts) VALUES (?,?,?,?,NULL,?)",
                (case_uid, account, json.dumps(signature, sort_keys=True),
                 verdict, _now()))

    def set_pattern_outcome(self, case_uid: str, outcome: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE patterns SET outcome=? WHERE case_uid=?",
                               (outcome, case_uid))

    def match_patterns(self, signature: dict, exclude_uid: str = "") -> list[dict]:
        """Prior cases with the EXACT same abstract signature (quantised
        structural features) — the institutional memory lookup."""
        sig = json.dumps(signature, sort_keys=True)
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM patterns WHERE signature=? AND case_uid!=?"
                " ORDER BY ts DESC LIMIT 20", (sig, exclude_uid)).fetchall()
        return [dict(r) | {"signature": json.loads(r["signature"])} for r in rows]

    def list_patterns(self, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM patterns ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) | {"signature": json.loads(r["signature"])} for r in rows]

    def prior_cases_for_account(self, account: str, exclude_uid: str = "") -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT uid, status, verdict, alert_type FROM cases"
                " WHERE account=? AND uid!=? ORDER BY created_at DESC LIMIT 10",
                (account, exclude_uid)).fetchall()
        return [dict(r) for r in rows]

    def kv_set(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?,?)", (key, value))

    def kv_get(self, key: str) -> str | None:
        with self._lock:
            r = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    # ── shaping ──────────────────────────────────────────────────────────────
    @staticmethod
    def _public(row: dict, full: bool = False) -> dict:
        out = dict(row)
        out["counterparties"] = json.loads(out.get("counterparties") or "[]")
        raw = out.pop("result_json", None)
        if full and raw:
            out["result"] = json.loads(raw)
        return out
