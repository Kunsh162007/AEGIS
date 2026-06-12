"""Chat Analyst (agent #15) — the desk you can talk to. Answers questions
about the org's data, cases and verdicts.

Grounding discipline: the agent first COMPUTES the relevant facts from the
casebook (cases, evidence, typologies, KPIs, org profile) and builds a
deterministic answer from them. In live-model mode the LLM may rephrase that
answer using ONLY the gathered facts; if the model is unavailable the
deterministic answer ships as-is. The model never gets to invent a number.
"""
from __future__ import annotations

import re

from ..config import settings
from ..knowledge.typologies import TYPOLOGIES
from .base import BaseAgent

_TOKEN = re.compile(r"[A-Za-z0-9_-]{2,}")


class ChatAnalystAgent(BaseAgent):
    name = "chat_analyst"
    tier = "reasoning"

    def __init__(self, model=None, store=None):
        super().__init__(model)
        self.store = store

    # ── fact gathering (pure computation) ───────────────────────────────────
    def _find_cases(self, question: str, rows: list[dict]) -> list[dict]:
        """Cases whose account or uid is literally mentioned in the question."""
        words = {w.lower() for w in _TOKEN.findall(question)}
        hits = [r for r in rows
                if r["account"].lower() in words or r["uid"].lower() in words]
        if not hits:  # substring fallback: 'mule-7' inside a longer token
            q = question.lower()
            hits = [r for r in rows if r["account"].lower() in q]
        return hits[:3]

    def _typology_matches(self, question: str) -> list[dict]:
        q = {w.lower() for w in _TOKEN.findall(question)}
        out = []
        for t in TYPOLOGIES:
            name = t["id"].split("/", 1)[-1]
            if name.replace("_", " ") in question.lower() or name in q or \
                    any(w in q for w in name.split("_")):
                out.append({"id": t["id"], "text": t["text"]})
        return out[:2]

    def _stats(self, rows: list[dict]) -> dict:
        by = lambda v: [r for r in rows if r["verdict"] == v]  # noqa: E731
        return {
            "cases_total": len(rows),
            "suspicious": len(by("suspicious")),
            "uncertain": len(by("uncertain")),
            "benign": len(by("benign")),
            "pending_review": sum(1 for r in rows if r["status"] == "pending_review"),
            "confirmed": sum(1 for r in rows if r["status"] == "confirmed_suspicious"),
            "dismissed": sum(1 for r in rows
                             if r["status"] == "dismissed_false_positive"),
        }

    def gather_facts(self, question: str) -> dict:
        rows = self.store.list(None, 200) if self.store else []
        facts: dict = {"stats": self._stats(rows)}

        mentioned = self._find_cases(question, rows)
        if mentioned:
            details = []
            for m in mentioned:
                full = self.store.get(m["uid"]) or {}
                result = full.get("result", {})
                details.append({
                    "uid": m["uid"], "account": m["account"],
                    "verdict": m["verdict"], "confidence": m["confidence"],
                    "alert_type": m["alert_type"], "status": m["status"],
                    "priority": m["priority"], "exposure": m["exposure"],
                    "rationale": result.get("rationale", ""),
                    "evidence": [e["claim"] for e in result.get("evidence", [])
                                 if e.get("verified")][:6],
                })
            facts["cases"] = details

        typologies = self._typology_matches(question)
        if typologies:
            facts["typologies"] = typologies

        org = self.store.get_org_profile() if self.store else None
        if org:
            facts["org_profile"] = org

        flagged = [r for r in rows if r["verdict"] in ("suspicious", "uncertain")]
        if flagged and not mentioned:
            facts["flagged_accounts"] = [
                {"account": r["account"], "verdict": r["verdict"],
                 "alert_type": r["alert_type"], "uid": r["uid"]}
                for r in flagged[:8]]
        return facts

    # ── answering ────────────────────────────────────────────────────────────
    def _deterministic_answer(self, question: str, facts: dict) -> str:
        parts: list[str] = []
        for c in facts.get("cases", []):
            parts.append(
                f"Account {c['account']} ({c['uid']}) was judged "
                f"{c['verdict'].upper()} at confidence {c['confidence']} "
                f"({c['alert_type']}, ${c['exposure']:,.0f} exposure, "
                f"status: {c['status']}). {c['rationale']}")
            if c["evidence"]:
                parts.append("Key verified evidence: "
                             + " | ".join(c["evidence"][:3]))
        for t in facts.get("typologies", []):
            parts.append(t["text"])
        if not parts:
            s = facts["stats"]
            if s["cases_total"] == 0:
                parts.append("The casebook is empty — run an analysis first, "
                             "then ask me about what was found.")
            else:
                parts.append(
                    f"{s['cases_total']} case(s) on file: {s['suspicious']} "
                    f"suspicious, {s['uncertain']} uncertain, {s['benign']} "
                    f"benign; {s['pending_review']} awaiting review, "
                    f"{s['confirmed']} confirmed, {s['dismissed']} dismissed.")
                if facts.get("flagged_accounts"):
                    parts.append("Flagged accounts: " + ", ".join(
                        f"{f['account']} ({f['alert_type']})"
                        for f in facts["flagged_accounts"]))
        return " ".join(parts)

    def answer(self, question: str) -> dict:
        facts = self.gather_facts(question)
        grounded = self._deterministic_answer(question, facts)

        text = grounded
        if settings.provider != "mock":
            prose = self.narrate(
                f"Question from the compliance officer: {question}\n\n"
                f"Established facts (answer ONLY from these; do not invent "
                f"numbers, accounts or verdicts):\n{grounded}",
                system="You are AEGIS's case analyst. Answer the question in "
                       "2-5 clear sentences using only the established facts "
                       "provided. Keep every count and number exactly as "
                       "stated in the facts. If the facts don't cover the "
                       "question, say so and suggest what to analyze.")
            # The model client degrades to a mock echo on provider failure —
            # detect that marker and keep the deterministic answer instead.
            if prose and not prose.startswith(f"[{self.name}]"):
                text = prose

        return {"answer": text, "facts": facts}
