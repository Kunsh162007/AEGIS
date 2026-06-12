"""The Department — one process-wide instance of everything that must persist
ACROSS investigations for the learning loop to be real: the autonomy policy
(tuned by every officer decision, reloaded on restart), the knowledge base
(re-seeded with reviewed precedent on startup), the casebook, and the feedback
loop. API requests and CLI runs build per-case Orchestrators from it, so every
new investigation reads the department's current tuned state.
"""
from __future__ import annotations

import threading

from ..config import settings
from ..data.schema import Case, CaseResult, Verdict
from ..feedback.loop import FeedbackLoop
from ..knowledge import KnowledgeBase
from ..policy.autonomy import AutonomyPolicy
from .priority import (MANUAL_MINUTES_PER_ALERT, REVIEW_MINUTES_WITH_AEGIS,
                       hours_saved)
from .store import CaseStore

_DECISIONS = {"confirm": (Verdict.SUSPICIOUS, "confirmed_suspicious"),
              "dismiss": (Verdict.BENIGN, "dismissed_false_positive")}


class Department:
    def __init__(self, db_path: str | None = None):
        self.store = CaseStore(db_path or settings.db_path)
        self.policy = AutonomyPolicy()
        saved = self.store.kv_get("clear_confidence")
        if saved:
            self.policy.clear_confidence = float(saved)
        self.kb = KnowledgeBase()
        for doc_id, text in self.store.precedents():
            self.kb.add_precedent(doc_id, text)
        self.feedback = FeedbackLoop(policy=self.policy, kb=self.kb)
        self._decide_lock = threading.Lock()

    def orchestrator(self):
        from ..orchestrator import Orchestrator  # late import: avoids a cycle
        return Orchestrator(policy=self.policy, kb=self.kb)

    def record_case(self, case: Case, result: CaseResult,
                    source_file: str = "") -> dict:
        return self.store.add_case(case, result, source_file)

    def decide(self, uid: str, decision: str) -> dict:
        """Apply the human officer's decision to a filed case: update its
        lifecycle, tune the autonomy thresholds, persist the reviewed precedent.
        This is the single point where human judgment enters the loop."""
        if decision not in _DECISIONS:
            raise ValueError("decision must be 'confirm' or 'dismiss'")
        with self._decide_lock:
            row = self.store.get(uid)
            if row is None:
                raise KeyError(f"no case {uid}")
            if row["status"] not in ("pending_review", "auto_cleared"):
                raise ValueError(f"case {uid} already decided ({row['status']})")

            verdict, status = _DECISIONS[decision]
            result = CaseResult.model_validate(row["result"])
            entry = self.feedback.record(result, verdict)

            self.store.set_decision(uid, verdict.value, status)
            self.store.add_feedback({**entry, "case_uid": uid})
            self.store.add_precedent(f"precedent/{result.case_id}", entry["precedent"])
            self.store.kv_set("clear_confidence", str(self.policy.clear_confidence))
        return {"case_uid": uid, "status": status,
                "officer_decision": verdict.value, "agreed": entry["agreed"],
                "clear_confidence_before": entry["clear_confidence_before"],
                "clear_confidence_after": entry["clear_confidence_after"]}

    def operations(self) -> dict:
        """The department's KPIs — the 'one human runs this' numbers, with the
        workload assumptions stated next to them."""
        by_status = self.store.counts_by_status()
        auto = by_status.get("auto_cleared", 0)
        pending = by_status.get("pending_review", 0)
        confirmed = by_status.get("confirmed_suspicious", 0)
        dismissed = by_status.get("dismissed_false_positive", 0)
        total = sum(by_status.values())
        reviewed = confirmed + dismissed
        return {
            "cases_total": total,
            "auto_cleared": auto,
            "pending_review": pending,
            "confirmed_suspicious": confirmed,
            "dismissed_false_positive": dismissed,
            "overdue_reviews": self.store.overdue_reviews(),
            "auto_clear_rate": round(auto / total, 3) if total else 0.0,
            "avg_qa_score": self.store.avg_qa_score(),
            "analyst_hours_saved": hours_saved(auto, reviewed),
            "workload_assumptions": {
                "manual_minutes_per_alert": MANUAL_MINUTES_PER_ALERT,
                "review_minutes_with_aegis": REVIEW_MINUTES_WITH_AEGIS,
            },
            "policy": {
                "clear_confidence": round(self.policy.clear_confidence, 3),
                "escalate_suspicion_floor": self.policy.escalate_suspicion_floor,
            },
            "recent_feedback": self.store.feedback_history(20),
        }


_department: Department | None = None
_lock = threading.Lock()


def get_department() -> Department:
    global _department
    with _lock:
        if _department is None:
            _department = Department()
        return _department


def reset_department() -> None:
    """Tests only — drop the singleton so the next call builds a fresh one."""
    global _department
    with _lock:
        _department = None
